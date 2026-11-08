"""Explicit public projections of existing computed results."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from bottleneck_analyzer.agents.contracts import (
    AnalyticsSummary,
    EvidenceInterpretation,
    ExecutionError,
    ExecutionEvent,
    Explanation,
    InvestigationResponse,
    Outcome,
    SampleStatistics,
    ScenarioExecution,
)
from bottleneck_analyzer.analytics.contracts import AggregateReference, AnalyticsScope, LineMetrics
from bottleneck_analyzer.retrieval.contracts import EvidenceAssessment, Relationship
from bottleneck_analyzer.workflows.answers import answer_paragraphs, source_excerpts


class DatasetView(BaseModel):
    id: UUID
    name: str
    provenance: str
    start_time: datetime
    end_time: datetime


class ShiftView(BaseModel):
    id: UUID
    name: str
    start_time: datetime
    end_time: datetime


class OptionsView(BaseModel):
    stations: list[str]
    models: list[str]
    shifts: list[ShiftView]
    shifts_truncated: bool
    methods: list[Literal["repair_duration", "failure_rate"]]
    simulation_max_days: int
    simulation_max_replications: int
    reduction_percentage_exclusive_maximum: int = 100


class SubmissionView(BaseModel):
    submission_key: UUID
    admission: str
    investigation_id: UUID | None
    worker_active: bool
    error: str | None
    process_local: Literal[True] = True


class AcceptedView(BaseModel):
    investigation_id: UUID
    submission_key: UUID
    status_url: str
    result_url: str


class HistoryView(BaseModel):
    id: UUID
    dataset_id: UUID
    question: str
    recorded_at: datetime


class ProgressView(BaseModel):
    investigation_id: UUID
    recorded_at: datetime
    persisted_status: str | None
    events: list[ExecutionEvent]
    final_confirmed: bool
    outcome: Outcome | None
    execution: Literal["active", "not_started", "unconfirmed", "finalized"]
    execution_is_process_local: Literal[True] = True


class EvidenceView(BaseModel):
    evidence_id: str
    dataset_id: UUID
    dataset_name: str
    provenance: str
    source_record_id: UUID
    source_system: str
    source_id: str
    source_type: str
    recorded_at: datetime
    station: str | None
    station_id: UUID | None
    text: str
    text_basis: str
    incident_id: UUID | None
    work_order_id: UUID | None
    recorded_cause: str | None
    historian_quality: str | None
    historian_value: float | None
    document_id: UUID | None
    document_version: str | None
    document_effective_at: datetime | None
    section_id: UUID | None
    section_sequence: int | None
    text_start: int
    text_end: int
    relationship: str
    relationship_basis: str
    links: list[Relationship]
    retrieval_methods: list[str]
    scores: dict[str, float]
    warnings: list[str]
    untrusted_content: Literal[True] = True


class EvidenceBundle(BaseModel):
    records: list[EvidenceView]
    assessments: list[EvidenceAssessment]
    interpretations: list[EvidenceInterpretation]
    methods_run: list[str]
    unavailable_methods: list[str]
    warnings: list[str]


class SimulationView(BaseModel):
    baseline: SampleStatistics
    scenario: SampleStatistics
    paired_gain: SampleStatistics
    seeds: list[int]
    configuration_version: str
    days: int
    scenario_request: dict | None
    realized_downtime_reduction_percentage: float | None
    throughput_improvement_percentage: float | None
    baseline_target_fault_seconds: float | None
    scenario_target_fault_seconds: float | None
    constraint_assessment: dict
    limitations: list[str]


class HistoricalProvenance(BaseModel):
    """Stored measurements and bounded source samples, never recomputed estimates."""

    line: LineMetrics
    provenance: str | None
    references: list[AggregateReference] = Field(max_length=50)
    assumptions: list[str] = Field(max_length=30)


class ResultView(BaseModel):
    investigation_id: UUID
    audit_id: UUID
    question: str
    scope: AnalyticsScope
    intent: str | None
    outcome: Outcome
    status: str
    answer: str
    historical: AnalyticsSummary | None
    evidence: EvidenceBundle | None
    simulation: SimulationView | None
    interpretation: Explanation | None
    clarification: str | None
    warnings: list[str]
    limitations: list[str]
    errors: list[ExecutionError]
    events: list[ExecutionEvent]
    human_review: str
    projection_notices: list[str] = Field(default_factory=list)
    historical_provenance: HistoricalProvenance | None = None


def confirmed(row: dict) -> bool:
    return str(row.get("audit_id")) == str(row["id"]) == str(row.get("response_id"))


def project_result(row: dict) -> ResultView:
    response = InvestigationResponse.model_validate(row["response"])
    data = response.model_dump(mode="json")
    notices = []
    composed = (
        response.interpretation is not None
        and response.interpretation.composition_version == "question_specific_v1"
    )
    if (
        not composed
        and response.intent is not None
        and response.outcome in ("completed", "incomplete")
    ):
        scenario = (
            ScenarioExecution.model_validate(row["scenario_request"]).request
            if row.get("scenario_request")
            else None
        )
        readable = "\n\n".join(
            [
                *answer_paragraphs(
                    response.intent,
                    response.historical,
                    response.evidence,
                    response.simulation,
                    scenario,
                ),
                *source_excerpts(response.evidence),
                response.human_review,
            ]
        )
        if readable != response.answer:
            data["answer"] = readable
            notices.append("Answer restated from saved findings for readability; audit unchanged.")
    if response.historical and row.get("historical_line"):
        references = []
        for station in (row.get("historical_stations") or [])[:7]:
            for reference in station.get("references", []):
                if str(reference["dataset_id"]) != str(response.historical.dataset_id):
                    raise ValueError("Historical reference dataset mismatch")
                references.append({**reference, "samples": reference.get("samples", [])[:5]})
        if len(references) > 50:
            notices.append("Historical references limited to 50; originals remain in audit.")
        data["historical_provenance"] = {
            "line": row["historical_line"],
            "provenance": row.get("historical_origin"),
            "references": references[:50],
            "assumptions": (row.get("historical_assumptions") or [])[:30],
        }
    if response.evidence:
        retrieval = response.evidence.retrieval
        records = []
        for evidence in retrieval.evidence[:50]:
            item = evidence.model_dump(mode="json", include=set(EvidenceView.model_fields))
            if len(item["text"]) > 8000:
                item["text"] = item["text"][:8000]
                notices.append(f"Passage truncated: {evidence.evidence_id}")
            item["links"] = item["links"][:50]
            records.append(item)
        data["evidence"] = {
            "records": records,
            "assessments": retrieval.assessments,
            "interpretations": response.evidence.interpretations,
            "methods_run": retrieval.diagnostics.methods_run,
            "unavailable_methods": list(retrieval.diagnostics.unavailable),
            "warnings": retrieval.diagnostics.warnings,
        }
    if response.simulation:
        simulation = response.simulation
        data["simulation"] = simulation.model_dump(exclude={"comparison"})
        data["simulation"]["scenario_request"] = row.get("scenario_request")
        for key in (
            "realized_downtime_reduction_percentage",
            "throughput_improvement_percentage",
            "baseline_target_fault_seconds",
            "scenario_target_fault_seconds",
        ):
            data["simulation"][key] = simulation.comparison.get(key)

    # Bound potentially long lists/text without computing or changing metrics.
    def bound(value):
        if isinstance(value, str) and len(value) > 16000:
            notices.append("Long text truncated in public projection; original remains in audit.")
            return value[:16000]
        if isinstance(value, list):
            if len(value) > 100:
                notices.append("List limited to 100 entries; original remains in audit.")
            return [bound(v) for v in value[:100]]
        if isinstance(value, dict):
            if len(value) > 100:
                raise ValueError("Public projection exceeds bounds")
            return {k: bound(v) for k, v in value.items()}
        return value

    data = bound(data)
    data["projection_notices"] = sorted(set(notices))
    result = ResultView.model_validate(data)
    if len(result.model_dump_json().encode()) > 524288:
        raise ValueError("Public projection exceeds bounds")
    return result
