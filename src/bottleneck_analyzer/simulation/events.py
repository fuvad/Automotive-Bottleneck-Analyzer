"""Exclusive station states and time-weighted measurements."""

from collections import defaultdict
from dataclasses import dataclass

from bottleneck_analyzer.simulation.calendars import Calendar


@dataclass(slots=True)
class StateInterval:
    station: int
    state: str
    start: float
    end: float


@dataclass(slots=True)
class Fault:
    station: int
    category: str
    equipment_id: str
    occurrence: int
    start: float
    end: float
    sampled_repair: float
    truncated: bool = False


class Gauge:
    def __init__(self, calendar: Calendar):
        self.calendar = calendar
        self.value = 0
        self.maximum = 0
        self.area = 0.0
        self.last = 0.0

    def update(self, time: float, value: int) -> None:
        self.area += self.value * self.calendar.scheduled_between(self.last, time)
        self.last = time
        self.value = value
        self.maximum = max(self.maximum, value)

    def finish(self) -> float:
        self.update(self.calendar.horizon, self.value)
        return self.area / self.calendar.scheduled_seconds


class StateRecorder:
    def __init__(self, calendar: Calendar, record: bool):
        self.calendar = calendar
        self.record = record
        self.raw = ["starved"] * 7
        self.current = ["starved" if calendar.position(0)[0] else "planned_downtime"] * 7
        self.since = [0.0] * 7
        self.durations = [defaultdict(float) for _ in range(7)]
        self.intervals: list[StateInterval] = []

    def set(self, station: int, state: str, now: float) -> None:
        self.raw[station] = state
        effective = state if self.calendar.position(now)[0] else "planned_downtime"
        if effective != self.current[station]:
            self._close(station, now)
            self.current[station] = effective

    def _close(self, station: int, now: float) -> None:
        duration = now - self.since[station]
        if duration > 1e-9:
            state = self.current[station]
            self.durations[station][state] += duration
            if self.record:
                self.intervals.append(StateInterval(station, state, self.since[station], now))
        self.since[station] = now

    def refresh(self, now: float) -> None:
        for index, state in enumerate(self.raw):
            self.set(index, state, now)

    def finish(self) -> None:
        for index in range(7):
            self._close(index, self.calendar.horizon)
