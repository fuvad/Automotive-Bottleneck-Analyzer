"""Interval algebra for persisted calendars; never infer working hours from dates."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from bottleneck_analyzer.analytics.contracts import AnalyticsScope

type Interval = tuple[datetime, datetime]


def merge(intervals: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def subtract(intervals: list[Interval], exclusions: list[Interval]) -> list[Interval]:
    result = merge(intervals)
    for a, b in merge(exclusions):
        next_result = []
        for start, end in result:
            if b <= start or a >= end:
                next_result.append((start, end))
            else:
                next_result.extend((x, y) for x, y in ((start, a), (b, end)) if y > x)
        result = next_result
    return result


def intersect(left: list[Interval], right: list[Interval]) -> list[Interval]:
    return merge([(max(a, c), min(b, d)) for a, b in left for c, d in right if a < d and c < b])


def seconds(intervals: list[Interval]) -> float:
    return sum((b - a).total_seconds() for a, b in merge(intervals))


def hourly(intervals: list[Interval], hours: list[int]) -> list[Interval]:
    result = []
    for start, end in intervals:
        cursor = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        while cursor < end:
            stop = cursor + timedelta(hours=1)
            if cursor.hour in hours:
                result.append((max(start, cursor), min(end, stop)))
            cursor = stop
    return merge(result)


@dataclass
class Segment:
    key: str
    kind: str
    label: str
    windows: list[Interval]
    scheduled: list[Interval]
    shift_id: UUID | None = None
    model: str | None = None
    utc_hour: int | None = None
    warnings: list[str] = field(default_factory=list)


def build_segments(
    dataset: dict, shifts: list[dict], exclusions: list[dict], scope: AnalyticsScope
) -> list[Segment]:
    start = scope.start_time or dataset["start_time"]
    end = scope.end_time or dataset["end_time"]
    if start < dataset["start_time"] or end > dataset["end_time"] or end <= start:
        raise ValueError("Analysis period must be inside the requested dataset")
    if scope.shift_id and not any(s["id"] == scope.shift_id for s in shifts):
        raise ValueError("Requested dated shift does not belong to this dataset")
    selected = [
        s
        for s in shifts
        if (not scope.shift or s["name"] == scope.shift)
        and (not scope.shift_id or s["id"] == scope.shift_id)
    ]
    windows = [(start, end)]
    if scope.shift or scope.shift_id:
        windows = intersect(windows, [(s["start_time"], s["end_time"]) for s in selected])
    if scope.utc_hours:
        windows = hourly(windows, scope.utc_hours)
    shift_windows = [(s["start_time"], s["end_time"]) for s in selected]
    scheduled = subtract(
        intersect(windows, shift_windows), [(e["start_time"], e["end_time"]) for e in exclusions]
    )
    results = [
        Segment("overall", "overall", "Selected production", windows, scheduled, model=scope.model)
    ]
    for s in selected:
        w = intersect(windows, [(s["start_time"], s["end_time"])])
        if w:
            results.append(
                Segment(
                    f"shift:{s['id']}",
                    "shift",
                    f"{s['start_time'].astimezone(UTC).isoformat()} {s['name']}",
                    w,
                    intersect(scheduled, w),
                    shift_id=s["id"],
                    model=scope.model,
                )
            )
    for model in ("SUV", "Sedan"):
        if scope.model is None or scope.model == model:
            results.append(
                Segment(f"model:{model}", "model", model, windows, scheduled, model=model)
            )
    for hour in range(24):
        if scope.utc_hours and hour not in scope.utc_hours:
            continue
        w = hourly(windows, [hour])
        if w:
            results.append(
                Segment(
                    f"hour:{hour:02d}",
                    "utc_hour",
                    f"{hour:02d}:00 UTC",
                    w,
                    intersect(scheduled, w),
                    model=scope.model,
                    utc_hour=hour,
                )
            )
    return results
