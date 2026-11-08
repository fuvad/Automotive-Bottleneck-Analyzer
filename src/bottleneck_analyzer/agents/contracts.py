"""Orchestration-only contracts; specialist results keep their existing types."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.analytics.contracts import AnalyticsResult, AnalyticsScope
from bottleneck_analyzer.domain.enums import InvestigationStatus, QuestionIntent
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES
from bottleneck_analyzer.domain.models import InvestigationState, ScenarioRequest
from bottleneck_analyzer.retrieval.contracts import Label, RetrievalResult
from bottleneck_analyzer.simulation.config import SimulationConfig

type AgentName = Literal["analytics", "knowledge", "simulation"]
type Outcome = Literal["completed", "incomplete", "clarification_required", "unsupported", "failed"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")


class ScenarioExecution(Contract):
    request: ScenarioRequest
    days: int | None = Field(default=None, ge=1, le=366)
    replications: int = Field(default=20, ge=2, le=50)
    seed_start: int = Field(default=1001, ge=0, le=2**31 - 100)
    sensitivity_days: int = Field(default=3, ge=1, le=30)
    sensitivity_replications: int = Field(default=5, ge=2, le=20)
    sensitivity_seed_start: int = Field(default=2001, ge=0, le=2**31 - 100)


class InvestigationRequest(Contract):
    question: str = Field(min_length=3, max_length=2000)
    scope: AnalyticsScope
    dataset_id: UUID | None = None
    scenario: ScenarioExecution | None = None
    incident_ids: list[UUID] = Field(default_factory=list, max_length=50)
    work_order_ids: list[UUID] = Field(default_factory=list, max_length=50)
    retrieval_limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def question_not_blank(self):
        if not self.question.strip():
            raise ValueError("Question must contain text")
        if self.scenario:
            validate_station(self.scenario.request.target_station)
        return self


class ScopeInterpretation(Contract):
    start_time: AwareDatetime | None
    end_time: AwareDatetime | None
    station: str | None
    model: Literal["SUV", "Sedan"] | None
    shift: Literal["shift_1", "shift_2"] | None
    utc_hours: list[int]


class PlanningInterpretation(Contract):
    intent: QuestionIntent | None
    unsupported: bool
    clarification: str | None
    scope: ScopeInterpretation
    target_station: str | None
    method: Literal["repair_duration", "failure_rate"] | None
    reduction_percentage: float | None


class InvestigationPlan(Contract):
    intent: QuestionIntent
    agents: list[AgentName]
    scope: AnalyticsScope
    scenario: ScenarioExecution | None = None


class DatasetContext(Contract):
    dataset_id: UUID
    name: str
    provenance: str
    content_hash: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    configuration_id: UUID | None = None
    configuration_approved: bool = False
    simulation_config: SimulationConfig | None = None


class EvidenceExcerpt(Contract):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=500)


class EvidenceInterpretation(Contract):
    station: str
    label: Label
    explanation: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(max_length=50)
    conflicting_evidence_ids: list[str] = Field(max_length=50)
    excerpts: list[EvidenceExcerpt] = Field(max_length=5)
    unresolved_questions: list[str] = Field(max_length=10)


class KnowledgeInput(Contract):
    analytics: AnalyticsResult
    stations: list[str] = Field(min_length=1, max_length=7)
    query: str = Field(max_length=1000)
    limit: int = Field(ge=1, le=50)
    incident_ids: list[UUID] = Field(default_factory=list, max_length=50)
    work_order_ids: list[UUID] = Field(default_factory=list, max_length=50)


class KnowledgeOutput(Contract):
    retrieval: RetrievalResult
    interpretations: list[EvidenceInterpretation]


class SampleStatistics(Contract):
    n: int = Field(ge=2)
    mean: float
    stdev: float = Field(ge=0)
    min: float
    max: float
    ci95: tuple[float, float]
    interval_method: str

    @model_validator(mode="after")
    def ordered_statistics(self):
        if not self.min <= self.mean <= self.max or not self.ci95[0] <= self.mean <= self.ci95[1]:
            raise ValueError("Sample statistics or interval bounds are inconsistent")
        return self


class SimulationInput(Contract):
    config: SimulationConfig
    scenario: ScenarioExecution


class SimulationOutput(Contract):
    baseline: SampleStatistics
    scenario: SampleStatistics
    paired_gain: SampleStatistics
    comparison: dict
    constraint_assessment: dict
    seeds: list[int]
    configuration_version: str
    days: int
    limitations: list[str]


class ExecutionError(Contract):
    component: str
    category: str
    message: str


class ExecutionEvent(Contract):
    component: str
    status: Literal["completed", "failed"]
    duration_seconds: float = Field(ge=0)
    category: str | None = None


class Explanation(Contract):
    """LLM wording references supplied facts; no model-generated numerical fields."""

    summary: str = Field(min_length=1, max_length=1600)
    evidence_ids: list[str] = Field(max_length=50)
    limitations: list[str] = Field(max_length=15)


class SegmentSummary(Contract):
    key: str
    kind: str
    label: str
    jph: float | None
    completed: int
    scheduled_hours: float
    leading_candidate: str | None
    warnings: list[str]


class AnalyticsSummary(Contract):
    dataset_id: UUID
    content_hash: str
    scope: AnalyticsScope
    leading_candidate: str | None
    historical_jph: float | None
    design_gap_jph: float | None
    scheduled_hours: float
    completed: int
    evidence_strength: str
    supporting_indicators: list[str]
    conflicting_indicators: list[str]
    aggregate_ids: list[str]
    candidate_changes: list[str]
    segments: list[SegmentSummary]


class InvestigationResponse(Contract):
    investigation_id: UUID
    question: str
    scope: AnalyticsScope
    intent: QuestionIntent | None
    outcome: Outcome
    status: InvestigationStatus
    answer: str
    historical: AnalyticsSummary | None = None
    evidence: KnowledgeOutput | None = None
    simulation: SimulationOutput | None = None
    interpretation: Explanation | None = None
    clarification: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    errors: list[ExecutionError] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)
    audit_id: UUID | None = None
    human_review: Literal[
        "Human review and approval are required before any operational change."
    ] = "Human review and approval are required before any operational change."

    @model_validator(mode="after")
    def completion_consistency(self):
        if self.outcome == "completed" and (
            self.errors or self.status != InvestigationStatus.COMPLETED or self.historical is None
        ):
            raise ValueError("Completed investigations require validated results without errors")
        if self.outcome == "completed":
            if self.intent is None:
                raise ValueError("Completed investigations require a supported intent")
            if (
                self.intent in (QuestionIntent.CAUSES, QuestionIntent.COMBINED)
                and self.evidence is None
            ):
                raise ValueError("Completed cause investigations require evidence results")
            if (
                self.intent in (QuestionIntent.WHAT_IF, QuestionIntent.COMBINED)
                and self.simulation is None
            ):
                raise ValueError("Completed what-if investigations require simulation results")
        if self.outcome == "clarification_required" and not self.clarification:
            raise ValueError("Clarification text is required")
        return self


class WorkflowState(InvestigationState):
    """Refines the Stage 1 state rather than creating another domain vocabulary."""

    request: InvestigationRequest
    scope: AnalyticsScope
    context: DatasetContext
    plan: InvestigationPlan | None = None
    analytics: AnalyticsResult | None = None
    knowledge: KnowledgeOutput | None = None
    simulation: SimulationOutput | None = None
    response: InvestigationResponse | None = None
    outcome: Outcome | None = None
    clarification: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[ExecutionError] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    execution_limits: dict[str, int] = Field(default_factory=dict)


def validate_station(station: str) -> str:
    if station not in STATION_NAMES:
        raise ValueError("Unknown station")
    return station
