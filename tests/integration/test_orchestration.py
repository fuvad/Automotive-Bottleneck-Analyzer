"""Actual graph/services/audit in the existing rollback-only PostgreSQL fixture."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select

from bottleneck_analyzer.agents.contracts import InvestigationRequest
from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.analytics.service import analyze_connection
from bottleneck_analyzer.core.config import AppSettings
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.db.models.production import InvestigationAudit
from bottleneck_analyzer.domain.enums import QuestionIntent
from bottleneck_analyzer.domain.manufacturing import DatasetConfig
from bottleneck_analyzer.retrieval.service import retrieve_connection
from bottleneck_analyzer.simulation.config import SimulationConfig
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.persistence import persist_result
from bottleneck_analyzer.workflows.audit import create_audit, dataset_context, save_audit
from bottleneck_analyzer.workflows.graph import InvestigationWorkflow

from .test_business_schema import schema_connection as schema_connection


class FixtureLLM:
    def __init__(self, intent):
        self.intent = intent

    def generate(self, instruction, data, schema):
        if schema.__name__ == "PlanningInterpretation":
            return schema.model_validate(
                {
                    "intent": self.intent,
                    "unsupported": False,
                    "clarification": None,
                    "scope": {
                        "start_time": None,
                        "end_time": None,
                        "station": None,
                        "model": None,
                        "shift": None,
                        "utc_hours": [],
                    },
                    "target_station": "Hemming",
                    "method": "repair_duration",
                    "reduction_percentage": 30,
                }
            )
        if schema.__name__ == "ScopedEvidenceSelection":
            return schema.model_validate({"evidence_ids": [e["id"] for e in data["evidence"]][:5]})
        return schema.model_validate(
            {
                "summary": data["allowed_summaries"][0],
                "evidence_ids": data["evidence_ids"],
                "limitations": [],
            }
        )


class ConnectionAudit:
    def __init__(self, connection):
        self.connection = connection

    def create(self, state):
        create_audit(self.connection, state)

    def save(self, state):
        save_audit(self.connection, state)


@pytest.fixture
def graph_case(schema_connection, monkeypatch):
    authored = generate_history(DatasetConfig(name="stage2-30day-v1", days=1, vehicles_per_shift=4))
    load_history(schema_connection, authored)
    config = SimulationConfig(name="stage6-integration", days=1, record_history=True)
    persist_result(schema_connection, run_simulation(config))
    monkeypatch.setattr(
        "bottleneck_analyzer.workflows.graph.load_context",
        lambda engine, scope: dataset_context(schema_connection, scope),
    )
    monkeypatch.setattr(
        "bottleneck_analyzer.agents.analytics.analyze",
        lambda engine, scope: analyze_connection(schema_connection, scope),
    )
    monkeypatch.setattr(
        "bottleneck_analyzer.agents.knowledge.retrieve",
        lambda engine, request, **kwargs: retrieve_connection(schema_connection, request, **kwargs),
    )
    return schema_connection, config


@pytest.mark.parametrize("intent", list(QuestionIntent))
def test_all_five_graph_workflows_and_durable_audit(graph_case, intent):
    connection, config = graph_case
    request = InvestigationRequest(
        question="Analyze Hemming robot repairs and a 30% repair duration reduction",
        scope=AnalyticsScope(dataset=config.name, station="Hemming"),
        retrieval_limit=10,
    )
    if intent in (QuestionIntent.WHAT_IF, QuestionIntent.COMBINED):
        request = InvestigationRequest.model_validate(
            {
                **request.model_dump(),
                "scenario": {
                    "request": {
                        "target_station": "Hemming",
                        "method": "repair_duration",
                        "reduction_percentage": 30,
                    },
                    "days": 1,
                    "replications": 2,
                    "sensitivity_days": 1,
                    "sensitivity_replications": 2,
                },
            }
        )
    if intent == QuestionIntent.SEGMENTATION:
        request.scope.model = "SUV"
        request.scope.shift = "shift_1"
    workflow = InvestigationWorkflow(
        Mock(),
        settings=AppSettings(_env_file=None),
        llm=FixtureLLM(intent),
        audit=ConnectionAudit(connection),
    )
    result = workflow.run(request)
    assert not result.errors
    assert result.outcome in ("completed", "incomplete")
    assert result.historical.dataset_id == workflow.latest.context.dataset_id
    if intent == QuestionIntent.SEGMENTATION:
        assert result.historical.scope.model == "SUV"
        assert result.historical.scope.shift == "shift_1"
    if intent in (QuestionIntent.CAUSES, QuestionIntent.COMBINED):
        assert result.evidence.retrieval.evidence
        assert result.evidence.interpretations
        for item in result.evidence.interpretations:
            assert item.unresolved_questions
            for excerpt in item.excerpts:
                assert excerpt.evidence_id in result.answer
        assert all(e.station == "Hemming" for e in result.evidence.retrieval.evidence)
    if intent in (QuestionIntent.WHAT_IF, QuestionIntent.COMBINED):
        assert result.simulation.baseline.n == 2
        assert (
            workflow.latest.simulation_parameters["scenario"]["request"]["method"]
            == "repair_duration"
        )
    audit = (
        connection.execute(
            select(InvestigationAudit.__table__).where(InvestigationAudit.id == result.audit_id)
        )
        .mappings()
        .one()
    )
    assert audit["state"]["validation_status"] == "validated"
    assert audit["state"]["response"]["audit_id"] == str(result.audit_id)
    assert audit["state"]["analytics"]["content_hash"] == workflow.latest.context.content_hash
    assert audit["final_answer"] == result.answer
    assert len(audit["state"]["events"]) == len(result.events)
    assert audit["state"]["model_versions"]["simulation"] == config.version
    assert audit["state"]["model_versions"]["llm_adapter"] == "FixtureLLM"


def test_dataset_and_foreign_shift_rejected_before_agent_calls(graph_case):
    connection, config = graph_case
    workflow = InvestigationWorkflow(
        Mock(),
        settings=AppSettings(_env_file=None),
        llm=FixtureLLM("constraint_output_loss"),
        audit=ConnectionAudit(connection),
    )
    for scope in [
        AnalyticsScope(dataset="does-not-exist"),
        AnalyticsScope(dataset=config.name, shift_id=uuid4()),
    ]:
        with pytest.raises(ValueError):
            workflow.run(InvestigationRequest(question="Analyze production", scope=scope))


def test_unconfigured_llm_failure_is_persisted(graph_case):
    connection, config = graph_case
    workflow = InvestigationWorkflow(
        Mock(), settings=AppSettings(_env_file=None), audit=ConnectionAudit(connection)
    )
    response = workflow.run(
        InvestigationRequest(
            question="Which station limits JPH?", scope=AnalyticsScope(dataset=config.name)
        )
    )
    assert response.outcome == "failed"
    assert response.errors[0].category == "LLMUnavailable"
    saved = connection.scalar(
        select(InvestigationAudit.state).where(InvestigationAudit.id == response.audit_id)
    )
    assert saved["response"]["outcome"] == "failed"
