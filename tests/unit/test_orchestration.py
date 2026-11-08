"""Deterministic agent/graph tests; no paid provider or public database writes."""

import io
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bottleneck_analyzer.agents.analytics import AnalyticsAgent
from bottleneck_analyzer.agents.contracts import (
    DatasetContext,
    Explanation,
    InvestigationPlan,
    InvestigationRequest,
    InvestigationResponse,
    KnowledgeOutput,
    PlanningInterpretation,
    ScenarioExecution,
    SimulationInput,
    WorkflowState,
)
from bottleneck_analyzer.agents.knowledge import EvidenceSelection
from bottleneck_analyzer.agents.planner import WORKFLOWS, PlannerAgent
from bottleneck_analyzer.agents.simulation import SimulationAgent, execute
from bottleneck_analyzer.analytics.contracts import (
    AnalyticsResult,
    AnalyticsScope,
    LineMetrics,
    SegmentResult,
)
from bottleneck_analyzer.core.config import AppSettings
from bottleneck_analyzer.core.llm import LLMUnavailable, OpenAIStructuredLLM, strict_schema
from bottleneck_analyzer.core.observability import WorkflowTelemetry
from bottleneck_analyzer.domain.enums import InvestigationStatus, QuestionIntent
from bottleneck_analyzer.domain.models import ScenarioRequest
from bottleneck_analyzer.retrieval.contracts import (
    Diagnostics,
    RetrievalRequest,
    RetrievalResult,
)
from bottleneck_analyzer.simulation.config import SimulationConfig
from bottleneck_analyzer.workflows.audit import AuditUnavailable
from bottleneck_analyzer.workflows.graph import InvestigationWorkflow
from bottleneck_analyzer.workflows.validation import validate_plan


class FixtureLLM:
    """Scripted structured responses, explicitly not a language-service fallback."""

    def __init__(self, default_intent=QuestionIntent.CONSTRAINT_OUTPUT_LOSS, **patch):
        self.intent = default_intent
        self.patch = patch
        self.calls = []

    def generate(self, instruction, data, schema):
        self.calls.append(schema.__name__)
        if schema is PlanningInterpretation:
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
                    **self.patch,
                }
            )
        if issubclass(schema, EvidenceSelection):
            return schema(evidence_ids=[e["id"] for e in data["evidence"]][:5])
        if issubclass(schema, Explanation):
            return schema(
                summary=data["allowed_summaries"][0],
                evidence_ids=data["evidence_ids"],
                limitations=[],
            )
        raise AssertionError(schema)


@pytest.fixture
def bundle():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    scope = AnalyticsScope(dataset="fixture", start_time=start, end_time=start + timedelta(days=1))
    context = DatasetContext(
        dataset_id=uuid4(),
        name="fixture",
        provenance="simulation",
        content_hash="unchanged",
        start_time=scope.start_time,
        end_time=scope.end_time,
        simulation_config=SimulationConfig(days=1),
    )
    segment = SegmentResult(
        key="overall",
        kind="overall",
        label="Overall",
        start_time=start,
        end_time=scope.end_time,
        line=LineMetrics(
            admitted=10,
            completed=10,
            initial_wip=0,
            final_wip=0,
            scheduled_hours=1,
            jph=10,
            design_rate_jph=60,
            design_gap_jph=50,
            design_gap_bodies=50,
            completion_counts_by_model={"SUV": 5, "Sedan": 5},
        ),
        stations=[],
        candidates=[],
        leading_candidate=None,
    )
    analytics = AnalyticsResult(
        dataset_id=context.dataset_id,
        dataset_name="fixture",
        provenance="simulation",
        content_hash="unchanged",
        scope=scope,
        overall=segment,
        segments=[],
        candidate_changes=[],
        warnings=[],
        assumptions=["Synthetic history"],
    )
    return scope, context, analytics


def make_workflow(
    monkeypatch, bundle, workflow_intent=QuestionIntent.CONSTRAINT_OUTPUT_LOSS, **patch
):
    scope, context, analytics = bundle
    monkeypatch.setattr("bottleneck_analyzer.workflows.graph.load_context", lambda *args: context)
    audit = Mock()
    workflow = InvestigationWorkflow(
        Mock(),
        settings=AppSettings(_env_file=None),
        llm=FixtureLLM(workflow_intent, **patch),
        audit=audit,
    )
    workflow.analytics.run = Mock(return_value=analytics)
    return workflow, InvestigationRequest(question="Which station limits production?", scope=scope)


@pytest.mark.parametrize("intent,agents", list(WORKFLOWS.items()))
def test_planner_registry_and_supported_intents(bundle, intent, agents):
    scope, context, _ = bundle
    state = WorkflowState(
        question="Analyze production",
        scope=scope,
        context=context,
        request=InvestigationRequest(question="Analyze production", scope=scope),
    )
    plan = PlannerAgent(FixtureLLM(intent)).plan(state)
    assert tuple(plan.agents) == agents
    validate_plan(plan)


def test_python_rejects_model_invented_agent_order(bundle):
    scope, _, _ = bundle
    with pytest.raises(ValueError, match="registry"):
        validate_plan(
            InvestigationPlan(intent="combined", agents=["simulation", "analytics"], scope=scope)
        )


@pytest.mark.parametrize(
    "intent", [QuestionIntent.CONSTRAINT_OUTPUT_LOSS, QuestionIntent.SEGMENTATION]
)
def test_real_graph_historical_and_segmentation(monkeypatch, bundle, intent):
    workflow, request = make_workflow(monkeypatch, bundle, intent)
    result = workflow.run(request)
    assert result.outcome == "completed"
    assert result.historical.historical_jph == 10
    assert [e.component for e in result.events] == ["planner", "analytics", "validation", "compose"]
    assert result.audit_id == result.investigation_id
    workflow.analytics.run.assert_called_once_with(request.scope)
    assert workflow.audit.save.call_count == 5
    assert workflow.latest.model_versions["llm_adapter"] == "FixtureLLM"
    assert workflow.latest.execution_limits["simulation_timeout_seconds"] == 600
    InvestigationResponse.model_validate(result.model_dump())


@pytest.mark.parametrize(
    "intent", [QuestionIntent.CAUSES, QuestionIntent.WHAT_IF, QuestionIntent.COMBINED]
)
def test_all_dependent_graph_routes(monkeypatch, bundle, intent):
    workflow, request = make_workflow(monkeypatch, bundle, intent)
    request.scope.station = "Hemming"
    bundle[2].scope = request.scope
    retrieval_request = RetrievalRequest(
        dataset="fixture",
        stations=["Hemming"],
        start_time=request.scope.start_time,
        end_time=request.scope.end_time,
    )
    retrieval = RetrievalResult(
        dataset_id=bundle[1].dataset_id,
        dataset_name="fixture",
        provenance="simulation",
        content_hash="unchanged",
        request=retrieval_request,
        evidence=[],
        assessments=[],
        diagnostics=Diagnostics(),
    )
    workflow.knowledge.run = Mock(
        return_value=KnowledgeOutput(retrieval=retrieval, interpretations=[])
    )
    scenario = ScenarioExecution(
        request=ScenarioRequest(
            target_station="Hemming", method="repair_duration", reduction_percentage=30
        ),
        days=1,
        replications=2,
        sensitivity_days=1,
        sensitivity_replications=2,
    )
    simulation = execute(SimulationInput(config=bundle[1].simulation_config, scenario=scenario))
    if "simulation" in WORKFLOWS[intent]:
        request.scenario = scenario
    workflow.simulation.run = Mock(return_value=simulation)
    response = workflow.run(request)
    assert response.outcome in ("completed", "incomplete")
    assert not response.errors
    order = [e.component for e in response.events]
    assert order == ["planner", *WORKFLOWS[intent], "validation", "compose"]
    if "simulation" in WORKFLOWS[intent]:
        assert response.simulation.baseline.n == 2
        assert response.historical.historical_jph == 10
        assert "Simulated paired means" in response.answer


def test_ambiguous_downtime_clarifies_without_provider_or_tools(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle, QuestionIntent.WHAT_IF)
    request.question = "What if robot-fault downtime is reduced by 30%?"
    response = workflow.run(request)
    assert response.outcome == "clarification_required"
    assert "repair duration" in response.clarification
    workflow.analytics.run.assert_not_called()
    assert workflow.planner.llm.calls == []


@pytest.mark.parametrize(
    "patch,outcome",
    [
        ({"unsupported": True}, "unsupported"),
        ({"intent": None, "clarification": "Which period?"}, "clarification_required"),
        ({"method": None}, "clarification_required"),
    ],
)
def test_unsupported_and_missing_scenario_parameters(monkeypatch, bundle, patch, outcome):
    workflow, request = make_workflow(monkeypatch, bundle, QuestionIntent.WHAT_IF, **patch)
    assert workflow.run(request).outcome == outcome
    workflow.analytics.run.assert_not_called()


def test_operational_write_is_refused(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    request.question = "Create a CMMS work order and execute PLC changes"
    assert workflow.run(request).outcome == "unsupported"
    workflow.analytics.run.assert_not_called()


def test_conflicting_scope_clarifies(monkeypatch, bundle):
    workflow, request = make_workflow(
        monkeypatch,
        bundle,
        scope={
            "start_time": None,
            "end_time": None,
            "station": "Framing",
            "model": None,
            "shift": None,
            "utc_hours": [],
        },
    )
    request.scope.station = "Hemming"
    assert workflow.run(request).outcome == "clarification_required"


def test_invalid_provider_planning_output_cannot_route(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    workflow.planner.llm = Mock()
    workflow.planner.llm.generate.return_value = Mock(model_dump=lambda: {"intent": "run_sql"})
    response = workflow.run(request)
    assert response.outcome == "failed"
    workflow.analytics.run.assert_not_called()


@pytest.mark.parametrize("component", ["planner", "analytics", "compose"])
def test_required_component_failure_is_not_success(monkeypatch, bundle, component):
    workflow, request = make_workflow(monkeypatch, bundle)
    if component == "analytics":
        workflow.analytics.run.side_effect = RuntimeError("secret database URL")
    elif component == "planner":
        workflow.planner.llm.generate = Mock(side_effect=LLMUnavailable("secret key"))
    else:
        workflow.planner.explain = Mock(side_effect=ValueError("invented citation"))
    response = workflow.run(request)
    assert response.outcome == "failed"
    assert response.status == InvestigationStatus.BLOCKED
    assert response.errors[0].component == component
    assert "secret" not in response.model_dump_json()


def test_graph_interruption_is_audited(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    workflow.graph = Mock(invoke=Mock(side_effect=RuntimeError("interrupted")))
    result = workflow.run(request)
    assert result.outcome == "failed"
    assert result.errors[0].component == "workflow"
    workflow.audit.save.assert_called_once()


def test_audit_failure_never_claims_completion(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    workflow.audit.save.side_effect = RuntimeError("offline")
    with pytest.raises(AuditUnavailable):
        workflow.run(request)


def test_foreign_dataset_uuid_fails_before_execution(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    request.dataset_id = uuid4()
    with pytest.raises(ValueError, match="UUID"):
        workflow.run(request)
    workflow.audit.create.assert_not_called()


def test_analytics_agent_uses_existing_service_and_rejects_scope_change(monkeypatch, bundle):
    scope, _, result = bundle
    service = Mock(return_value=result)
    monkeypatch.setattr("bottleneck_analyzer.agents.analytics.analyze", service)
    agent = AnalyticsAgent(Mock())
    assert agent.run(scope) == result
    service.assert_called_once_with(agent.engine, scope)
    result.dataset_name = "foreign"
    with pytest.raises(ValueError, match="scope"):
        agent.run(scope)


@pytest.mark.parametrize("method", ["repair_duration", "failure_rate"])
def test_simulation_agent_executes_real_existing_engine_in_worker(method):
    config = SimulationConfig(days=1, record_history=False)
    request = SimulationInput(
        config=config,
        scenario=ScenarioExecution(
            request=ScenarioRequest(
                target_station="Hemming", method=method, reduction_percentage=30
            ),
            days=1,
            replications=2,
            sensitivity_days=1,
            sensitivity_replications=2,
        ),
    )
    before = config.model_dump()
    result = SimulationAgent(AppSettings(_env_file=None, simulation_timeout_seconds=60)).run(
        request
    )
    assert result.seeds == [1001, 1002]
    assert result.baseline.n == 2
    assert result.paired_gain.mean == pytest.approx(result.scenario.mean - result.baseline.mean)
    assert result.comparison["scenario_config"]["intervention"]["method"] == method
    assert config.model_dump() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"replications": 21},
        {"days": 31},
        {
            "request": {
                "target_station": "unknown",
                "method": "repair_duration",
                "reduction_percentage": 30,
            }
        },
        {"request": {"target_station": "Hemming", "method": None, "reduction_percentage": 30}},
        {
            "request": {
                "target_station": "Hemming",
                "method": "repair_duration",
                "reduction_percentage": 100,
            }
        },
    ],
)
def test_simulation_invalid_or_excessive_parameters(changes):
    request = SimulationInput(
        config=SimulationConfig(),
        scenario=ScenarioExecution.model_validate(
            {
                "request": {
                    "target_station": "Hemming",
                    "method": "repair_duration",
                    "reduction_percentage": 30,
                },
                **changes,
            }
        ),
    )
    with pytest.raises(ValueError):
        SimulationAgent(AppSettings(_env_file=None)).run(request)


def test_optional_tracing_does_not_construct_client(monkeypatch):
    client = Mock(side_effect=AssertionError("network not permitted"))
    monkeypatch.setattr("bottleneck_analyzer.core.observability.Client", client)
    assert WorkflowTelemetry(AppSettings(_env_file=None)).client is None
    client.assert_not_called()
    assert WorkflowTelemetry(AppSettings(_env_file=None, langsmith_tracing=True)).unavailable


def test_traces_are_metadata_only_and_failure_is_optional(monkeypatch, bundle):
    from bottleneck_analyzer.agents.contracts import ExecutionEvent

    client = Mock()
    monkeypatch.setattr("bottleneck_analyzer.core.observability.Client", Mock(return_value=client))
    telemetry = WorkflowTelemetry(
        AppSettings(_env_file=None, langsmith_tracing=True, langsmith_api_key="private-key")
    )
    scope, context, _ = bundle
    state = WorkflowState(
        question="private source text",
        scope=scope,
        context=context,
        request=InvestigationRequest(question="private source text", scope=scope),
    )
    event = ExecutionEvent(component="analytics", status="completed", duration_seconds=1)
    telemetry.emit(state, event)
    kwargs = client.create_run.call_args.kwargs
    assert kwargs["inputs"] == {}
    metadata = kwargs["extra"]["metadata"]
    assert metadata["investigation_id"] == str(state.investigation_id)
    assert "private" not in json.dumps(kwargs, default=str)
    client.create_run.side_effect = ConnectionError("offline")
    telemetry.emit(state, event)
    assert telemetry.unavailable


@pytest.mark.parametrize(
    "available,payload,error",
    [
        (False, None, TimeoutError),
        (True, (False, "failed"), RuntimeError),
    ],
)
def test_simulation_worker_timeout_and_failure_cleanup(monkeypatch, available, payload, error):
    process = Mock(pid=123)
    process.is_alive.return_value = True
    receive, send = Mock(), Mock()
    receive.poll.return_value = available
    receive.recv.return_value = payload
    context = Mock()
    context.Pipe.return_value = receive, send
    context.Process.return_value = process
    monkeypatch.setattr(
        "bottleneck_analyzer.agents.simulation.multiprocessing.get_context",
        Mock(return_value=context),
    )
    request = SimulationInput(
        config=SimulationConfig(days=1),
        scenario=ScenarioExecution(
            request=ScenarioRequest(
                target_station="Hemming", method="repair_duration", reduction_percentage=30
            ),
            days=1,
            replications=2,
        ),
    )
    with pytest.raises(error):
        SimulationAgent(AppSettings(_env_file=None)).run(request)
    process.terminate.assert_called_once()
    process.join.assert_called_once()
    process.close.assert_called_once()


@pytest.mark.parametrize(
    "component,intent",
    [
        ("knowledge", QuestionIntent.CAUSES),
        ("simulation", QuestionIntent.WHAT_IF),
    ],
)
def test_specialist_failure_prevents_complete_answer(monkeypatch, bundle, component, intent):
    workflow, request = make_workflow(monkeypatch, bundle, intent)
    request.scope.station = "Hemming"
    bundle[2].scope = request.scope
    getattr(workflow, component).run = Mock(side_effect=RuntimeError("specialist failure"))
    result = workflow.run(request)
    assert result.outcome == "failed"
    assert result.errors[0].component == component
    assert workflow.latest.validation_status != "validated"


def test_mismatched_numbers_fail_shared_validation(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    bundle[2].overall.line.jph = 99
    result = workflow.run(request)
    assert result.outcome == "failed"
    assert result.errors[0].component == "validation"
    assert result.historical is None


def test_llm_unsupported_final_citation_is_rejected(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    original = workflow.planner.llm.generate

    def wrong_citation(instruction, data, schema):
        output = original(instruction, data, schema)
        if issubclass(schema, Explanation):
            output.evidence_ids = ["invented"]
        return output

    workflow.planner.llm.generate = wrong_citation
    result = workflow.run(request)
    assert result.outcome == "failed"
    assert result.errors[0].component == "compose"


def test_llm_missing_configuration_fails_clearly():
    with pytest.raises(LLMUnavailable, match="not configured"):
        OpenAIStructuredLLM(AppSettings(_env_file=None)).generate("Plan", {}, Explanation)


def test_llm_http_contract_and_strict_validation(monkeypatch):
    captured = []
    output = {"summary": "Grounded introduction", "evidence_ids": [], "limitations": []}
    payload = {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(output)}]}
        ],
    }

    def http(request, timeout):
        captured.append(json.loads(request.data))
        assert timeout == 30
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("bottleneck_analyzer.core.llm.urlopen", http)
    adapter = OpenAIStructuredLLM(
        AppSettings(
            _env_file=None,
            llm_provider="openai",
            llm_model="configured-model",
            llm_api_key="fixture",
        )
    )
    assert adapter.generate("Plan", {}, Explanation).summary == output["summary"]
    assert captured[0]["store"] is False
    assert "tools" not in captured[0]
    assert captured[0]["text"]["format"]["strict"] is True
    payload["status"] = "incomplete"
    with pytest.raises(LLMUnavailable):
        adapter.generate("Plan", {}, Explanation)
    payload["status"] = "completed"
    payload["output"][0]["content"][0]["text"] = '{"invented":true}'
    with pytest.raises(LLMUnavailable):
        adapter.generate("Plan", {}, Explanation)


def test_strict_schema_marks_nullable_fields_required():
    schema = strict_schema(PlanningInterpretation.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert "default" not in json.dumps(schema)


@pytest.mark.parametrize(
    "field,value",
    [
        ("question", " "),
        ("question", "x" * 2001),
        ("retrieval_limit", 51),
        ("scope", {"dataset": "fixture", "start_time": "2026-09-01T00:00:00"}),
    ],
)
def test_investigation_input_validation(bundle, field, value):
    with pytest.raises(ValidationError):
        InvestigationRequest.model_validate(
            {"question": "Analyze production", "scope": bundle[0], field: value}
        )
