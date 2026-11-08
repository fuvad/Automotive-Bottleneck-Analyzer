"""The bounded SimPy line and controlled vehicle release process."""

from collections import Counter

import simpy

from bottleneck_analyzer.simulation.buffer import Buffer
from bottleneck_analyzer.simulation.calendars import Calendar
from bottleneck_analyzer.simulation.config import SimulationConfig
from bottleneck_analyzer.simulation.events import Gauge, StateRecorder
from bottleneck_analyzer.simulation.failures import stream
from bottleneck_analyzer.simulation.station import Station
from bottleneck_analyzer.simulation.vehicle import Vehicle


class Line:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.env = simpy.Environment()
        self.calendar = Calendar(config)
        self.states = StateRecorder(self.calendar, config.record_history)
        self.queue_gauges = [Gauge(self.calendar) for _ in range(7)]
        self.buffers = [
            Buffer(self.env, capacity, gauge)
            for capacity, gauge in zip(
                (config.input_capacity, *config.buffer_capacities), self.queue_gauges, strict=True
            )
        ]
        self.wip = Gauge(self.calendar)
        self.released = 0
        self.completed = 0
        self.operation_counts = [0] * 7
        self.completed_work = [0.0] * 7
        self.faults = []
        self.vehicles = []
        self.models = Counter()
        self.shifts = Counter()
        self.hourly = Counter()
        self.flow_sum = 0.0
        self.cycle_sum = 0.0
        self.last_completion = None
        self.stations = [Station(self, index) for index in range(7)]

    def calendar_changes(self):
        for boundary in self.calendar.boundaries[1:]:
            yield self.env.timeout(boundary - self.env.now)
            self.states.refresh(self.env.now)

    def wait_scheduled(self, duration: float):
        while duration > 1e-7:
            opened, boundary = self.calendar.position(self.env.now)
            if not opened:
                yield self.env.timeout(max(1e-7, boundary - self.env.now))
            else:
                step = min(duration, boundary - self.env.now)
                yield self.env.timeout(step)
                duration -= step

    def release(self):
        mix = stream(self.config.seed, "vehicle-mix")
        arrivals = stream(self.config.seed, "arrivals")
        sequence = 0
        while True:
            opened, boundary = self.calendar.position(self.env.now)
            if not opened:
                yield self.env.timeout(max(1e-7, boundary - self.env.now))
                continue
            sequence += 1
            vehicle = Vehicle(
                sequence,
                "SUV" if mix.random() < self.config.suv_fraction else "Sedan",
                self.env.now,
                self.env.now,
            )
            yield self.buffers[0].put(vehicle)
            vehicle.release = self.env.now
            vehicle.arrival = self.env.now
            self.released += 1
            self.wip.update(self.env.now, self.wip.value + 1)
            if self.config.record_history:
                self.vehicles.append(vehicle)
            interval = 3600 / self.config.release_rate_jph
            if self.config.release_pattern == "exponential":
                interval = arrivals.expovariate(1 / interval)
            yield from self.wait_scheduled(interval)

    def complete(self, vehicle: Vehicle) -> None:
        vehicle.completion = self.env.now
        self.completed += 1
        self.models[vehicle.model] += 1
        window = self.calendar.shift_at(max(0, self.env.now - 1e-7))
        self.shifts[f"{window.day}/{window.name}"] += 1
        self.hourly[str(int(self.env.now // 3600))] += 1
        self.flow_sum += self.env.now - vehicle.release
        if self.last_completion is not None:
            self.cycle_sum += self.calendar.scheduled_between(self.last_completion, self.env.now)
        self.last_completion = self.env.now
        self.wip.update(self.env.now, self.wip.value - 1)

    def run(self):
        self.env.process(self.calendar_changes())
        for station in self.stations:
            self.env.process(station.run())
        self.env.process(self.release())
        self.env.run(until=self.calendar.horizon)
        self.states.finish()
