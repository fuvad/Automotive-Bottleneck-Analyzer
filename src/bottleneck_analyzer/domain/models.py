"""Foundational typed contracts shared by later application stages."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.domain.enums import (
    EvidenceRelationship,
    InterventionMethod,
    InvestigationStatus,
    QuestionIntent,
)


class AnalysisScope(BaseModel):
    """Optional filters that define the population being investigated."""

    model_config = ConfigDict(extra="forbid")

    start_time: datetime | None = None
    end_time: datetime | None = None
    model: str | None = None
    shift: str | None = None
    station: str | None = None
    time_of_day: str | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "AnalysisScope":
        """Prevent an inverted analysis period."""
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EvidenceReference(BaseModel):
    """A traceable source reference returned by a later analysis or retrieval stage."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    relationship: EvidenceRelationship
    excerpt: str | None = None


class ScenarioRequest(BaseModel):
    """Validated scenario parameters without executing a simulation."""

    model_config = ConfigDict(extra="forbid")

    target_station: str = Field(min_length=1)
    fault_category: str = "robot_fault"
    method: InterventionMethod | None = None
    reduction_percentage: float = Field(gt=0, le=100)
    baseline_version: str | None = None


class InvestigationState(BaseModel):
    """Shared, serializable state passed between future workflow components."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: UUID = Field(default_factory=uuid4)
    question: str = Field(min_length=1)
    intent: QuestionIntent | None = None
    scope: AnalysisScope = Field(default_factory=AnalysisScope)
    status: InvestigationStatus = InvestigationStatus.PENDING
    plan: list[str] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    retrieved_evidence: list[EvidenceReference] = Field(default_factory=list)
    simulation_parameters: dict[str, Any] = Field(default_factory=dict)
    validation_status: str = "not_validated"
    evidence_ids: list[str] = Field(default_factory=list)
