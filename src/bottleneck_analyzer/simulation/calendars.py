"""Calendar intervals and scheduled-time arithmetic in seconds from the start."""

from bisect import bisect_right
from dataclasses import dataclass

from bottleneck_analyzer.simulation.config import SimulationConfig


@dataclass(frozen=True, slots=True)
class Window:
    day: int
    name: str
    start: float
    end: float
    break_start: float
    break_end: float


class Calendar:
    def __init__(self, config: SimulationConfig):
        self.horizon = config.days * 86400.0
        self.windows = [
            Window(
                day,
                s.name,
                day * 86400 + s.start_seconds,
                day * 86400 + s.start_seconds + s.duration_seconds,
                day * 86400 + s.start_seconds + s.break_start_seconds,
                day * 86400 + s.start_seconds + s.break_start_seconds + s.break_seconds,
            )
            for day in range(config.days)
            for s in config.shifts
        ]
        self.open_intervals = sorted(
            (a, b)
            for w in self.windows
            for a, b in ((w.start, w.break_start), (w.break_end, w.end))
            if b > a
        )
        self.starts = [a for a, _ in self.open_intervals]
        self.ends = [b for _, b in self.open_intervals]
        self.boundaries = sorted({0.0, self.horizon, *self.starts, *self.ends})
        self.prefix = [0.0]
        for a, b in self.open_intervals:
            self.prefix.append(self.prefix[-1] + b - a)

    @property
    def scheduled_seconds(self) -> float:
        return self.prefix[-1]

    def position(self, time: float) -> tuple[bool, float]:
        i = bisect_right(self.starts, time) - 1
        if i >= 0 and time < self.ends[i]:
            return True, self.ends[i]
        next_index = bisect_right(self.starts, time)
        return False, self.starts[next_index] if next_index < len(self.starts) else self.horizon

    def cumulative(self, time: float) -> float:
        i = bisect_right(self.starts, time) - 1
        if i < 0:
            return 0.0
        return self.prefix[i] + max(0.0, min(time, self.ends[i]) - self.starts[i])

    def scheduled_between(self, start: float, end: float) -> float:
        return self.cumulative(end) - self.cumulative(start)

    def shift_at(self, time: float) -> Window | None:
        day = int(time // 86400)
        for w in self.windows[day * 2 : day * 2 + 2]:
            if w.start <= time < w.end:
                return w
        return None
