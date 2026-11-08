"""Validated synthetic assumptions; no database access or simulation on import."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.domain.enums import InterventionMethod
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES, FaultCategory


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Distribution(Parameters):
    mean: float = Field(gt=0)
    cv: float = Field(default=0.08, ge=0, le=2)
    minimum: float = Field(default=1, gt=0)

    @model_validator(mode="after")
    def check_minimum(self):
        if self.minimum > self.mean:
            raise ValueError("minimum cannot exceed the configured mean")
        return self


class Failure(Parameters):
    category: FaultCategory = FaultCategory.ROBOT_FAULT
    equipment_id: str = Field(default="robot", min_length=1, max_length=40)
    mtbf_seconds: float = Field(default=30000, gt=0)
    repair: Distribution = Distribution(mean=120, cv=0.35, minimum=10)


class StationParameters(Parameters):
    name: str
    processing: Distribution = Distribution(mean=60, minimum=30)
    suv_multiplier: float = Field(default=1.04, gt=0)
    sedan_multiplier: float = Field(default=0.96, gt=0)
    failures: tuple[Failure, ...] = (Failure(),)

    @model_validator(mode="after")
    def check_failures(self):
        if self.name not in STATION_NAMES:
            raise ValueError("Unknown station")
        keys = [(f.category, f.equipment_id) for f in self.failures]
        if len(keys) != len(set(keys)):
            raise ValueError("Failure category/equipment pairs must be unique")
        return self


class ShiftPattern(Parameters):
    name: Literal["shift_1", "shift_2"]
    start_seconds: float = Field(ge=0, lt=86400)
    duration_seconds: float = Field(default=28800, gt=0)
    break_start_seconds: float = Field(default=14400, ge=0)
    break_seconds: float = Field(default=1800, ge=0)

    @model_validator(mode="after")
    def check_window(self):
        if self.start_seconds + self.duration_seconds > 86400:
            raise ValueError("Shift must fit within its calendar day")
        if self.break_start_seconds + self.break_seconds > self.duration_seconds:
            raise ValueError("Break must be inside the shift")
        if self.break_seconds >= self.duration_seconds:
            raise ValueError("Each shift must contain scheduled production time")
        return self


class Intervention(Parameters):
    station: str
    category: FaultCategory = FaultCategory.ROBOT_FAULT
    equipment_id: str = "robot"
    method: InterventionMethod
    reduction_percentage: float = Field(default=30, gt=0, lt=100)


def initial_stations() -> tuple[StationParameters, ...]:
    means = (54, 59, 55, 56, 60, 55, 54)
    result = []
    for name, mean in zip(STATION_NAMES, means, strict=True):
        robot = Failure(
            mtbf_seconds=2400 if name == "Hemming" else 30000,
            repair=Distribution(mean=360 if name == "Hemming" else 120, cv=0.35, minimum=10),
        )
        other = tuple(
            Failure(
                category=category,
                equipment_id=category.value,
                mtbf_seconds=120000,
                repair=Distribution(mean=90, cv=0.3, minimum=10),
            )
            for category in (
                FaultCategory.MECHANICAL_FAULT,
                FaultCategory.ELECTRICAL_FAULT,
                FaultCategory.SENSOR_FAULT,
                FaultCategory.OTHER_EQUIPMENT_FAULT,
            )
        )
        result.append(
            StationParameters(
                name=name, processing=Distribution(mean=mean, minimum=30), failures=(robot, *other)
            )
        )
    return tuple(result)


class SimulationConfig(Parameters):
    name: str = Field(default="sim-30day-baseline-v1", pattern=r"^[a-zA-Z0-9_-]+$", max_length=100)
    seed: int = Field(default=1001, ge=0)
    start_time: AwareDatetime = datetime(2026, 9, 1, tzinfo=UTC)
    days: int = Field(default=30, ge=1, le=366)
    version: str = "simpy-line-v1"
    stations: tuple[StationParameters, ...] = Field(default_factory=initial_stations)
    buffer_capacities: tuple[int, ...] = (5, 5, 5, 5, 5, 5)
    input_capacity: int = Field(default=5, ge=1, le=1000)
    release_rate_jph: float = Field(default=65, gt=0, le=300)
    release_pattern: Literal["periodic", "exponential"] = "periodic"
    suv_fraction: float = Field(default=0.5, ge=0, le=1)
    shifts: tuple[ShiftPattern, ...] = (
        ShiftPattern(name="shift_1", start_seconds=0),
        ShiftPattern(name="shift_2", start_seconds=28800),
    )
    intervention: Intervention | None = None
    record_history: bool = True
    sop_reference_dataset: str = "stage2-30day-v1"
    calibration_status: str = "not_calibrated"

    @model_validator(mode="after")
    def validate_line(self):
        if tuple(s.name for s in self.stations) != STATION_NAMES:
            raise ValueError("Exactly seven stations in the agreed sequence are required")
        if len(self.buffer_capacities) != 6 or any(
            isinstance(c, bool) or c < 1 for c in self.buffer_capacities
        ):
            raise ValueError("Six positive finite buffer capacities are required")
        if len(self.shifts) != 2 or {s.name for s in self.shifts} != {"shift_1", "shift_2"}:
            raise ValueError("Exactly two shift patterns are required")
        ordered = sorted(self.shifts, key=lambda s: s.start_seconds)
        if ordered[0].start_seconds + ordered[0].duration_seconds > ordered[1].start_seconds:
            raise ValueError("Shifts cannot overlap")
        if (
            self.start_time.utcoffset() != timedelta(0)
            or self.start_time.time().isoformat() != "00:00:00"
        ):
            raise ValueError("Simulation starts at midnight UTC")
        if self.intervention is not None:
            target = self.intervention
            matching = [
                f
                for s in self.stations
                if s.name == target.station
                for f in s.failures
                if f.category == target.category and f.equipment_id == target.equipment_id
            ]
            if len(matching) != 1:
                raise ValueError("Scenario must identify one configured station/category/equipment")
        return self

    @property
    def end_time(self) -> datetime:
        return self.start_time + timedelta(days=self.days)


def updated(config: SimulationConfig, **changes) -> SimulationConfig:
    return SimulationConfig.model_validate({**config.model_dump(), **changes})
