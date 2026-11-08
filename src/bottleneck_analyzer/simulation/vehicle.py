"""Compact business entities; identity is stable throughout station traversal."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Operation:
    station: int
    arrival: float
    start: float
    processing_seconds: float
    end: float | None = None
    departure: float | None = None


@dataclass(slots=True)
class Vehicle:
    sequence: int
    model: str
    release: float
    arrival: float
    operations: list[Operation] = field(default_factory=list)
    completion: float | None = None
