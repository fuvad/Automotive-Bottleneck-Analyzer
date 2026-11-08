"""Station workers: processing suspension, serialized repairs and blocking after service."""

import math

from bottleneck_analyzer.domain.enums import InterventionMethod
from bottleneck_analyzer.simulation.events import Fault
from bottleneck_analyzer.simulation.failures import sample, stream
from bottleneck_analyzer.simulation.vehicle import Operation

EPS = 1e-7


class Station:
    def __init__(self, line, index: int):
        self.line = line
        self.env = line.env
        self.index = index
        self.parameters = line.config.stations[index]
        self.gaps = [
            stream(line.config.seed, index, f.category, f.equipment_id, "gaps")
            for f in self.parameters.failures
        ]
        self.repairs = [
            stream(line.config.seed, index, f.category, f.equipment_id, "repairs")
            for f in self.parameters.failures
        ]
        self.counts = [0] * len(self.parameters.failures)
        self.budgets = [self.next_gap(i) for i in range(len(self.gaps))]

    def targeted(self, failure) -> bool:
        target = self.line.config.intervention
        return target is not None and (
            target.station == self.parameters.name
            and target.category == failure.category
            and target.equipment_id == failure.equipment_id
        )

    def next_gap(self, index: int) -> float:
        failure = self.parameters.failures[index]
        mean = failure.mtbf_seconds
        target = self.line.config.intervention
        if self.targeted(failure) and target.method == InterventionMethod.FAILURE_RATE:
            mean /= 1 - target.reduction_percentage / 100
        return max(EPS, self.gaps[index].expovariate(1 / mean))

    def wait_open(self):
        opened, boundary = self.line.calendar.position(self.env.now)
        if not opened:
            yield self.env.timeout(max(EPS, boundary - self.env.now))

    def repair(self, index: int):
        failure = self.parameters.failures[index]
        self.counts[index] += 1
        duration = sample(failure.repair, self.repairs[index])
        target = self.line.config.intervention
        if self.targeted(failure) and target.method == InterventionMethod.REPAIR_DURATION:
            duration *= 1 - target.reduction_percentage / 100
        start = self.env.now
        observed_end = min(start + duration, self.line.calendar.horizon)
        fault = Fault(
            self.index,
            failure.category.value,
            failure.equipment_id,
            self.counts[index],
            start,
            observed_end,
            duration,
            start + duration > self.line.calendar.horizon,
        )
        self.line.faults.append(fault)
        self.line.states.set(self.index, "faulted", self.env.now)
        yield self.env.timeout(duration)  # Calendar-time repair; processing clock is suspended.
        self.budgets[index] = self.next_gap(index)
        self.line.states.set(self.index, "running", self.env.now)

    def process(self, work: float):
        remaining = work
        while remaining > EPS:
            yield from self.wait_open()
            if self.budgets:
                failure_index = min(range(len(self.budgets)), key=self.budgets.__getitem__)
                if self.budgets[failure_index] <= EPS:
                    yield from self.repair(failure_index)
                    continue
                fault_budget = self.budgets[failure_index]
            else:
                fault_budget = math.inf
            _, boundary = self.line.calendar.position(self.env.now)
            duration = min(remaining, fault_budget, boundary - self.env.now)
            if duration <= EPS:
                yield self.env.timeout(EPS)
                continue
            self.line.states.set(self.index, "running", self.env.now)
            yield self.env.timeout(duration)
            remaining -= duration
            for i in range(len(self.budgets)):
                self.budgets[i] -= duration

    def run(self):
        incoming = self.line.buffers[self.index]
        outgoing = self.line.buffers[self.index + 1] if self.index < 6 else None
        while True:
            yield from self.wait_open()
            self.line.states.set(self.index, "starved", self.env.now)
            vehicle = yield incoming.get()
            yield from self.wait_open()
            multiplier = (
                self.parameters.suv_multiplier
                if vehicle.model == "SUV"
                else self.parameters.sedan_multiplier
            )
            work = sample(
                self.parameters.processing,
                stream(self.line.config.seed, self.index, vehicle.sequence, "processing"),
            )
            work *= multiplier
            operation = Operation(self.index, vehicle.arrival, self.env.now, work)
            vehicle.operations.append(operation)
            yield from self.process(work)
            operation.end = self.env.now
            self.line.operation_counts[self.index] += 1
            self.line.completed_work[self.index] += work
            if outgoing is not None:
                self.line.states.set(self.index, "blocked", self.env.now)
                yield outgoing.put(vehicle)
            else:
                self.line.complete(vehicle)
            operation.departure = self.env.now
            vehicle.arrival = self.env.now
