"""HTTP/outcome separation, safe projections and local access boundaries."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from bottleneck_analyzer.api.runtime import Submission
from bottleneck_analyzer.api.schemas import confirmed, project_result
from bottleneck_analyzer.main import app


def audit_row(outcome="completed", final=True):
    identifier, dataset_id = uuid4(), uuid4()
    historical = {
        "dataset_id": str(dataset_id),
        "content_hash": "fixture",
        "scope": {"dataset": "fixture"},
        "leading_candidate": "Hemming",
        "historical_jph": 46.88,
        "design_gap_jph": 13.12,
        "scheduled_hours": 450,
        "completed": 21096,
        "evidence_strength": "strong",
        "supporting_indicators": [],
        "conflicting_indicators": [],
        "aggregate_ids": [],
        "candidate_changes": [],
        "segments": [],
    }
    response = {
        "investigation_id": str(identifier),
        "question": "Analyze line",
        "scope": {"dataset": "fixture"},
        "intent": "constraint_output_loss",
        "outcome": outcome,
        "status": "completed" if outcome == "completed" else "blocked",
        "answer": "Fixture answer",
        "historical": historical,
        "audit_id": str(identifier) if final else None,
        "clarification": "Choose a method" if outcome == "clarification_required" else None,
    }
    return {
        "id": identifier,
        "dataset_id": dataset_id,
        "recorded_at": datetime.now(UTC),
        "events": [
            {"component": "planner", "status": "completed", "duration_seconds": 1, "category": None}
        ],
        "status": response["status"],
        "audit_id": response["audit_id"],
        "response_id": str(identifier),
        "outcome": outcome,
        "response": response,
    }


@pytest.fixture
def client(monkeypatch):
    repo = Mock()
    monkeypatch.setattr("bottleneck_analyzer.api.routes.repository", lambda request: repo)
    with TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as client:
        yield client, repo


@pytest.mark.parametrize(
    "outcome", ["completed", "incomplete", "clarification_required", "unsupported", "failed"]
)
def test_all_outcomes_are_successful_reads_with_distinct_payloads(client, outcome):
    client, repo = client
    row = audit_row(outcome)
    repo.audit.return_value = row
    result = client.get(f"/api/investigations/{row['id']}/result")
    assert result.status_code == 200, result.text
    assert result.json()["outcome"] == outcome
    progress = client.get(f"/api/investigations/{row['id']}").json()
    assert progress["final_confirmed"] and progress["outcome"] == outcome
    assert progress["events"] == row["events"]
    assert "percentage" not in progress and "updated_at" not in progress


def test_completed_compose_checkpoint_and_restart_are_not_final(client):
    client, repo = client
    row = audit_row(final=False)
    repo.audit.return_value = row
    assert not confirmed(row)
    response = client.get(f"/api/investigations/{row['id']}/result")
    assert response.status_code == 409
    assert client.get(f"/api/investigations/{row['id']}").json()["outcome"] is None
    app.state.investigations.execution = lambda identifier: "active"
    assert client.get(f"/api/investigations/{row['id']}/result").status_code == 202


def test_wrong_persisted_response_id_is_not_final(client):
    client, repo = client
    row = audit_row()
    row["response_id"] = str(uuid4())
    repo.audit.return_value = row
    assert client.get(f"/api/investigations/{row['id']}/result").status_code == 409


def test_historical_provenance_copies_counts_and_bounds_samples():
    row = audit_row()
    row["historical_line"] = {
        "admitted": 21100,
        "completed": 21096,
        "initial_wip": 0,
        "final_wip": 4,
        "scheduled_hours": 450,
        "jph": 46.88,
        "design_rate_jph": 60,
        "design_gap_jph": 13.12,
        "design_gap_bodies": 5904,
        "completion_counts_by_model": {"SUV": 10000, "Sedan": 11096},
    }
    sample = {
        "evidence_id": "source:1",
        "source_type": "SCADA",
        "source_id": "raw-1",
        "relationship": "direct",
        "excerpt": "Original stored source",
    }
    reference = {
        "aggregate_id": "aggregate:1",
        "dataset_id": str(row["dataset_id"]),
        "segment_key": "overall",
        "measurement": "state coverage",
        "record_count": 123,
        "samples": [sample] * 8,
    }
    row["historical_stations"] = [{"references": [reference] * 60}]
    row["historical_origin"] = "simulation"
    result = project_result(row)
    assert result.historical_provenance.line.jph == 46.88
    assert result.historical_provenance.line.scheduled_hours == 450
    assert len(result.historical_provenance.references) == 50
    assert len(result.historical_provenance.references[0].samples) == 5
    assert result.historical_provenance.references[0].record_count == 123
    assert result.projection_notices
    reference["dataset_id"] = str(uuid4())
    with pytest.raises(ValueError, match="dataset mismatch"):
        project_result(row)


def test_saved_segmentation_answer_includes_comparison_without_changing_audit():
    from copy import deepcopy

    row = audit_row()
    row["response"]["intent"] = "segmentation"
    row["response"]["historical"]["segments"] = [
        {
            "key": "model:SUV",
            "kind": "model",
            "label": "SUV",
            "jph": 23.25,
            "completed": 10461,
            "scheduled_hours": 450,
            "leading_candidate": "Framing",
            "warnings": [],
        },
    ]
    before = deepcopy(row)
    result = project_result(row)
    assert result.answer.startswith("For the vehicle models, SUV points to Framing")
    assert result.historical.segments[0].jph == 23.25
    assert result.projection_notices and row == before
    row["response"]["answer"] = result.answer
    assert project_result(row).answer == result.answer  # No repeated prefix on refresh.


def test_question_specific_answer_is_not_replaced_by_legacy_category_presentation():
    row = audit_row()
    text = "Queues build before the candidate, while earlier stations are blocked."
    row["response"]["answer"] = text
    row["response"]["interpretation"] = {
        "summary": text,
        "evidence_ids": [],
        "limitations": [],
        "fact_ids": ["historical.support.0"],
        "composition_version": "question_specific_v1",
    }
    result = project_result(row)
    assert result.answer == text
    assert result.interpretation.fact_ids == ["historical.support.0"]
    assert not result.projection_notices


def test_database_errors_are_sanitized_and_liveness_independent(client):
    client, repo = client
    repo.datasets.side_effect = OperationalError("private SQL", {}, Exception("password=SECRET"))
    result = client.get("/api/datasets")
    assert result.status_code == 503
    assert "SECRET" not in result.text and "private SQL" not in result.text
    assert client.get("/health").status_code == 200


def test_invalid_input_pagination_and_missing_records(client):
    client, repo = client
    assert client.get("/api/datasets?limit=51").status_code == 422
    assert client.get("/api/investigations?offset=-1").status_code == 422
    assert client.get("/api/investigations/invalid").status_code == 422
    repo.audit.return_value = None
    assert client.get(f"/api/investigations/{uuid4()}").status_code == 404
    response = client.post("/api/investigations", json={"question": "PRIVATE INPUT"})
    assert response.status_code == 422 and "PRIVATE INPUT" not in response.text


def test_submission_reconciles_uncertain_committed_row_without_execution(client):
    client, repo = client
    from time import monotonic

    item = Submission(
        uuid4(),
        "fixture",
        monotonic() - 1,
        candidate_id=uuid4(),
        worker_active=False,
        abandoned=True,
        error="commit_unconfirmed",
    )
    app.state.investigations._items[item.key] = item
    repo.audit.return_value = {"id": item.candidate_id}
    response = client.get(f"/api/submissions/{item.key}")
    assert response.status_code == 200
    assert response.json()["admission"] == "rejected_execution_not_started"
    assert response.json()["investigation_id"] == str(item.candidate_id)
    assert not item.accepted


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Host": "evil.example:8000"}, 400),
        ({"Host": "localhost:9000"}, 400),
        ({"Origin": "https://evil.example"}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": "http://localhost:8000"}, 403),
        ({"Origin": "http://127.0.0.1:8000"}, 200),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
    ],
)
def test_local_access_boundaries(client, headers, status):
    client, repo = client
    repo.datasets.return_value = []
    response = client.get("/api/datasets", headers=headers)
    assert response.status_code == status
    assert "access-control-allow-origin" not in response.headers


def test_preflight_body_limits_static_safety_and_security_headers(client):
    client, repo = client
    assert client.options("/api/investigations").status_code == 403
    assert (
        client.post(
            "/api/investigations", content="x", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/investigations", content="x" * 32769, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    response = client.get("/")
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert client.get("/static/../../.env").status_code == 404
    assert client.get("/static/.env").status_code == 404
    assert client.get("/static/render.mjs").status_code == 200
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert css.headers["content-type"].split(";")[0] == "text/css"
    assert css.headers["x-content-type-options"] == "nosniff"
    assert "style-src 'self'" in css.headers["content-security-policy"]


def test_projection_keeps_numbers_and_removes_private_state():
    row = audit_row()
    result = project_result(row)
    assert result.historical.historical_jph == 46.88
    assert result.historical.design_gap_jph == 13.12
    assert "state" not in result.model_dump()


def test_supported_launcher_rejects_external_binding_and_reload(monkeypatch):
    from bottleneck_analyzer.api import cli
    from bottleneck_analyzer.core.config import AppSettings

    for patch in ({"app_host": "0.0.0.0"}, {"app_reload": True}):
        monkeypatch.setattr(cli, "get_settings", lambda: AppSettings(_env_file=None, **patch))
        with pytest.raises(SystemExit):
            cli.main()
    monkeypatch.setattr(cli, "get_settings", lambda: AppSettings(_env_file=None))
    run = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    cli.main()
    assert run.call_args.kwargs["workers"] == 1
    assert run.call_args.kwargs["reload"] is False
    assert run.call_args.kwargs["proxy_headers"] is False
