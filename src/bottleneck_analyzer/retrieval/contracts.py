"""Bounded evidence contracts; retrieved text is always untrusted source data."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.domain.enums import EvidenceRelationship
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES

type Method = Literal["exact", "lexical", "semantic"]
type Label = Literal[
    "recorded_maintenance_cause",
    "observed_association",
    "supported_hypothesis",
    "insufficient_evidence",
]
type System = Literal["CMMS", "Andon", "shift_notes", "historian", "SOP", "SCADA", "MES"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RetrievalRequest(Contract):
    dataset: str = Field(min_length=1)
    stations: list[str] = Field(default_factory=list, max_length=7)
    station_ids: list[UUID] = Field(default_factory=list, max_length=7)
    start_time: AwareDatetime
    end_time: AwareDatetime
    incident_ids: list[UUID] = Field(default_factory=list, max_length=50)
    work_order_ids: list[UUID] = Field(default_factory=list, max_length=50)
    source_record_ids: list[UUID] = Field(default_factory=list, max_length=100)
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)
    systems: list[System] = Field(
        default_factory=lambda: ["CMMS", "Andon", "shift_notes", "historian", "SOP", "SCADA"],
        min_length=1,
        max_length=7,
    )
    methods: list[Method] = Field(
        default_factory=lambda: ["exact", "lexical", "semantic"], min_length=1, max_length=3
    )
    utc_hours: list[int] = Field(default_factory=list, max_length=24)
    shift: Literal["shift_1", "shift_2"] | None = None
    shift_id: UUID | None = None
    maximum_cosine_distance: float = Field(default=0.5, ge=0, le=2)

    @model_validator(mode="after")
    def validate_scope(self) -> "RetrievalRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if not self.stations and not self.station_ids:
            raise ValueError("Select candidate stations explicitly")
        if any(s not in STATION_NAMES for s in self.stations):
            raise ValueError("Unknown station name")
        if any(h < 0 or h > 23 for h in self.utc_hours):
            raise ValueError("UTC hours must be in 0..23")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("Retrieval methods must be unique")
        return self


class Relationship(Contract):
    relationship: EvidenceRelationship
    basis: str = Field(min_length=1)
    from_source_id: UUID | None = None
    to_source_id: UUID | None = None


class Evidence(Contract):
    evidence_id: str
    dataset_id: UUID
    dataset_name: str
    provenance: str
    source_record_id: UUID
    source_system: System
    source_id: str
    source_type: str
    original_path: str | None
    recorded_at: AwareDatetime
    station_id: UUID | None
    station: str | None
    text: str
    original_text: str = ""
    text_basis: Literal["original_source_text", "sop_content", "normalized_record_fields"] = (
        "original_source_text"
    )
    raw_metadata: dict
    incident_id: UUID | None = None
    work_order_id: UUID | None = None
    recorded_cause: str | None = None
    historian_quality: str | None = None
    historian_value: float | None = None
    document_id: UUID | None = None
    document_version: str | None = None
    document_effective_at: AwareDatetime | None = None
    section_id: UUID | None = None
    section_sequence: int | None = None
    text_start: int = 0
    text_end: int
    retrieval_methods: list[Method]
    scores: dict[str, float] = Field(default_factory=dict)
    relationship: EvidenceRelationship
    relationship_basis: str
    links: list[Relationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    untrusted_content: Literal[True] = True


class CandidateContext(Contract):
    """Only the necessary Stage 4 fields; no parallel metric calculation."""

    station: str
    dataset_id: UUID
    start_time: AwareDatetime
    end_time: AwareDatetime
    model: str | None = None
    aggregate_ids: list[str]
    indicators: dict[str, float | None]
    supporting_indicators: list[str]
    conflicting_indicators: list[str]
    sample_strength: str


class EvidenceAssessment(Contract):
    station: str
    label: Label
    statement: str
    evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    candidate_context: CandidateContext | None = None
    warnings: list[str]


class Diagnostics(Contract):
    methods_run: list[Method] = Field(default_factory=list)
    unavailable: dict[str, str] = Field(default_factory=dict)
    match_counts: dict[str, int] = Field(
        default_factory=lambda: {"exact": 0, "lexical": 0, "semantic": 0}
    )
    unique_before_limit: int = 0
    returned: int = 0
    duplicates_merged: int = 0
    truncated: bool = False
    filters: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RetrievalResult(Contract):
    dataset_id: UUID
    dataset_name: str
    provenance: str
    content_hash: str
    request: RetrievalRequest
    evidence: list[Evidence]
    assessments: list[EvidenceAssessment]
    diagnostics: Diagnostics
