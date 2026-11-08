"""Actual PostgreSQL audit/projection checks in a rollback-only isolated schema."""

from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bottleneck_analyzer.agents.contracts import InvestigationRequest, WorkflowState
from bottleneck_analyzer.api.repository import APIRepository
from bottleneck_analyzer.api.runtime import AdmissionAudit, Submission
from bottleneck_analyzer.api.schemas import confirmed
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.db.models.production import InvestigationAudit
from bottleneck_analyzer.domain.manufacturing import DatasetConfig
from bottleneck_analyzer.workflows.audit import PostgresAudit, dataset_context

from .test_business_schema import schema_connection as schema_connection
from .test_orchestration import FixtureLLM
from .test_orchestration import graph_case as graph_case


def test_real_postgresql_audit_transaction_finishes_before_admission(schema_connection):
    connection = schema_connection
    history = generate_history(
        DatasetConfig(name="stage7-transaction", days=1, vehicles_per_shift=2)
    )
    load_history(connection, history)
    request = InvestigationRequest(
        question="Analyze fixture", scope={"dataset": history.config.name}
    )
    state = WorkflowState(
        question=request.question,
        request=request,
        scope=request.scope,
        context=dataset_context(connection, request.scope),
    )
    committed = Event()

    class IsolatedEngine:
        @contextmanager
        def begin(self):
            # RELEASE SAVEPOINT exercises the delegate's real transaction exit.
            # Outer rollback preserves public data; this is NOT a durable commit test.
            with connection.begin_nested():
                yield connection
            committed.set()

    item = Submission(uuid4(), "fixture", monotonic() + 5)
    delegate = PostgresAudit(IsolatedEngine())
    returned = Event()

    def worker():
        AdmissionAudit(delegate, item).create(state)
        returned.set()

    thread = Thread(target=worker)
    thread.start()
    assert committed.wait(3)
    # Worker no longer touches the connection while waiting at admission.
    assert connection.get_nested_transaction() is None
    assert connection.scalar(select(InvestigationAudit.id)) == state.investigation_id
    assert not returned.is_set()
    assert item.accept()
    thread.join(3)
    assert returned.is_set()


def test_actual_select_only_catalog_and_checkpoint_projection(schema_connection):
    connection = schema_connection
    history = generate_history(DatasetConfig(name="stage7-reader", days=1, vehicles_per_shift=2))
    load_history(connection, history)
    request = InvestigationRequest(
        question="Analyze fixture", scope={"dataset": history.config.name}
    )
    state = WorkflowState(
        question=request.question,
        request=request,
        scope=request.scope,
        context=dataset_context(connection, request.scope),
    )
    from bottleneck_analyzer.workflows.audit import create_audit, save_audit

    create_audit(connection, state)

    class Repository(APIRepository):
        @contextmanager
        def read(self):
            yield connection

    repo = Repository(Mock())
    assert len(repo.datasets(20, 0)) == 1
    assert len(repo.options(history.dataset_id)["stations"]) == 7
    assert repo.options(uuid4()) is None
    assert repo.history(1, 0)[0]["id"] == state.investigation_id
    assert not confirmed(repo.audit(state.investigation_id))
    from bottleneck_analyzer.agents.contracts import ExecutionEvent

    state.events = [ExecutionEvent(component="planner", status="completed", duration_seconds=0.5)]
    save_audit(connection, state)
    row = repo.audit(state.investigation_id, result=True)
    assert row["events"][0]["duration_seconds"] == 0.5
    assert not confirmed(row)
    assert repo.audit(uuid4()) is None


@pytest.mark.parametrize("intent", ["constraint_output_loss", "segmentation", "causes"])
def test_http_submission_uses_real_graph_and_isolated_audit(graph_case, monkeypatch, intent):
    from bottleneck_analyzer.api.runtime import InvestigationRuntime
    from bottleneck_analyzer.core.config import AppSettings
    from bottleneck_analyzer.main import app
    from bottleneck_analyzer.workflows.graph import InvestigationWorkflow

    connection, config = graph_case

    class IsolatedEngine:
        @contextmanager
        def begin(self):
            with connection.begin_nested():
                yield connection

    runtime = InvestigationRuntime(
        engine_factory=Mock,
        audit_factory=lambda engine: PostgresAudit(IsolatedEngine()),
        workflow_factory=lambda engine, audit: InvestigationWorkflow(
            engine, settings=AppSettings(_env_file=None), llm=FixtureLLM(intent), audit=audit
        ),
    )

    class Repository(APIRepository):
        @contextmanager
        def read(self):
            yield connection

    monkeypatch.setattr("bottleneck_analyzer.main.InvestigationRuntime", lambda: runtime)
    monkeypatch.setattr(
        "bottleneck_analyzer.api.routes.repository", lambda request: Repository(Mock())
    )
    key = uuid4()
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        accepted = client.post(
            "/api/investigations",
            headers={"X-Submission-Key": str(key)},
            json={
                "question": "Analyze Hemming production and evidence",
                "scope": {"dataset": config.name, "station": "Hemming"},
            },
        )
        assert accepted.status_code == 202, accepted.text
        item = runtime.get(key)
        deadline = monotonic() + 20
        while item.worker_active:
            assert monotonic() < deadline
            Event().wait(0.01)
        # The worker is finished before the caller reads its connection.
        response = client.get(accepted.json()["result_url"])
        assert response.status_code == 200, response.text
        assert response.json()["intent"] == intent
        assert response.json()["outcome"] in ("completed", "incomplete")
        assert response.json()["audit_id"] == accepted.json()["investigation_id"]
        assert response.json()["interpretation"]["composition_version"] == "question_specific_v1"
        stored = connection.scalar(
            select(InvestigationAudit.state).where(
                InvestigationAudit.id == accepted.json()["investigation_id"]
            )
        )
        assert response.json()["answer"] == stored["response"]["answer"]
        assert response.json()["interpretation"]["fact_ids"]
        saved = client.get(accepted.json()["status_url"]).json()
        assert saved["final_confirmed"] and saved["events"]
        duplicate = client.post(
            "/api/investigations",
            headers={"X-Submission-Key": str(key)},
            json={
                "question": "Analyze Hemming production and evidence",
                "scope": {"dataset": config.name, "station": "Hemming"},
            },
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["investigation_id"] == accepted.json()["investigation_id"]
