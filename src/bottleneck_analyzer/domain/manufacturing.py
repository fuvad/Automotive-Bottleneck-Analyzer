"""Manufacturing vocabulary and reproducible fixture configuration."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

STATION_NAMES = (
    "Underbody Welding",
    "Framing",
    "Roof Welding",
    "Closures Fitting",
    "Hemming",
    "Sealing",
    "Final Inspection",
)


class StationState(StrEnum):
    RUNNING = "running"
    BLOCKED = "blocked"
    STARVED = "starved"
    FAULTED = "faulted"
    PLANNED_DOWNTIME = "planned_downtime"


class FaultCategory(StrEnum):
    ROBOT_FAULT = "robot_fault"
    QUALITY_STOP = "quality_stop"
    MATERIAL_SHORTAGE = "material_shortage"


class DatasetConfig(BaseModel):
    """A dataset identity is immutable; choose another name for fresh data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(default="stage2-30day-v1", pattern=r"^[a-zA-Z0-9_-]+$", max_length=100)
    seed: int = Field(default=42, ge=0)
    start_time: AwareDatetime = datetime(2026, 9, 1, tzinfo=UTC)
    days: int = Field(default=30, ge=1, le=366)
    vehicles_per_shift: int = Field(default=345, ge=2, le=400)
    fault_focus: str | None = None
    generator_version: str = "authored-fixture-v1"

    @model_validator(mode="after")
    def validate_fixture(self) -> "DatasetConfig":
        if self.start_time.utcoffset() != timedelta(0):
            raise ValueError("start_time must use UTC")
        if self.start_time.time().isoformat() != "00:00:00":
            raise ValueError("start_time must be midnight UTC")
        if self.fault_focus is not None and self.fault_focus not in STATION_NAMES:
            raise ValueError("fault_focus must name an expected station")
        return self

    @property
    def end_time(self) -> datetime:
        return self.start_time + timedelta(days=self.days)
