"""Serializable historical analytics contracts, independent of ORM and agents."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.domain.manufacturing import STATION_NAMES
from bottleneck_analyzer.domain.models import AnalysisScope, EvidenceReference


class AnalyticsScope(AnalysisScope):
    """Explicit dataset plus validated refinements of the shared scope."""

    dataset: str = Field(min_length=1)
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    model: Literal["SUV", "Sedan"] | None = None
    shift: Literal["shift_1", "shift_2"] | None = None
    shift_id: UUID | None = None
    time_of_day: None = None
    utc_hours: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_filters(self) -> "AnalyticsScope":
        if self.station is not None and self.station not in STATION_NAMES:
            raise ValueError("Unknown station")
        if len(set(self.utc_hours)) != len(self.utc_hours) or any(
            h < 0 or h > 23 for h in self.utc_hours
        ):
            raise ValueError("utc_hours must be unique UTC hours in 0..23")
        return self


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AggregateReference(ResultModel):
    aggregate_id: str
    dataset_id: UUID
    segment_key: str
    station_id: UUID | None = None
    measurement: str
    record_count: int = Field(ge=0)
    samples: list[EvidenceReference] = Field(default_factory=list)


class LineMetrics(ResultModel):
    admitted: int = Field(ge=0)
    completed: int = Field(ge=0)
    initial_wip: int = Field(ge=0)
    final_wip: int = Field(ge=0)
    scheduled_hours: float = Field(ge=0)
    jph: float | None
    design_rate_jph: float = Field(ge=0)
    design_gap_jph: float | None
    design_gap_bodies: float | None
    completion_counts_by_model: dict[str, int]
    average_flow_seconds: float | None = None
    average_wip: float | None = None
    maximum_wip: int | None = None


class StationMetrics(ResultModel):
    station_id: UUID
    station: str
    sequence: int
    operations: int = Field(ge=0)
    scheduled_seconds: float = Field(ge=0)
    processing_seconds: float | None = None
    utilization: float | None = None
    faulted_seconds: float | None = None
    planned_closure_seconds: float | None = None
    blocked_seconds: float | None = None
    starved_seconds: float | None = None
    state_count: int = 0
    state_coverage: float | None = None
    overlap_seconds: float | None = None
    service_sample_count: int = 0
    mean_service_seconds: float | None = None
    processing_capacity_jph: float | None = None
    effective_capacity_jph: float | None = None
    mean_operation_elapsed_seconds: float | None = None
    mean_waiting_wall_seconds: float | None = None
    mean_blocked_wall_seconds: float | None = None
    average_input_queue: float | None = None
    maximum_input_queue: int | None = None
    input_capacity: int | None = None
    queue_basis: str
    references: list[AggregateReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Candidate(ResultModel):
    station: str
    rank: int
    score: float
    indicators: dict[str, float | None]
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    strength: Literal["strong", "moderate", "weak", "insufficient_evidence"]
    operations: int
    state_coverage: float | None
    dated_shift_leader_fraction: float | None = None
    dated_shifts_evaluated: int = 0
    dated_shifts_resolved: int = 0
    explanation: str
    aggregate_ids: list[str]


class SegmentResult(ResultModel):
    key: str
    kind: Literal["overall", "shift", "model", "utc_hour"]
    label: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    shift_id: UUID | None = None
    model: str | None = None
    utc_hour: int | None = None
    line: LineMetrics
    stations: list[StationMetrics]
    candidates: list[Candidate]
    leading_candidate: str | None
    warnings: list[str] = Field(default_factory=list)


class AnalyticsResult(ResultModel):
    dataset_id: UUID
    dataset_name: str
    provenance: str
    content_hash: str
    scope: AnalyticsScope
    overall: SegmentResult
    segments: list[SegmentResult]
    candidate_changes: list[str]
    simulation_evidence: list[dict] = Field(default_factory=list)
    warnings: list[str]
    assumptions: list[str]
