"""Check foundation contracts without contacting a database server."""

from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bottleneck_analyzer.core.config import AppSettings
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.session import create_db_engine, create_session_factory
from bottleneck_analyzer.domain.enums import (
    EvidenceRelationship,
    InterventionMethod,
    QuestionIntent,
)
from bottleneck_analyzer.domain.models import (
    AnalysisScope,
    EvidenceReference,
    InvestigationState,
    ScenarioRequest,
)
from bottleneck_analyzer.main import app

DATABASE_URL = "postgresql+psycopg://test_user:test_password@localhost:5432/test_db"


def test_package_and_application_imports() -> None:
    """Starter packages and FastAPI entry point import successfully."""
    assert import_module("bottleneck_analyzer.agents") is not None
    assert import_module("bottleneck_analyzer.simulation.engine") is not None
    assert app.title == "Automotive Bottleneck Analyzer"


def test_settings_accept_only_psycopg_postgresql() -> None:
    """Settings accept the planned driver and reject a different database."""
    settings = AppSettings(_env_file=None, database_url=DATABASE_URL)
    assert settings.database_url == DATABASE_URL
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, database_url="sqlite:///not-allowed.db")


def test_settings_include_rates_runtime_and_provider_configuration() -> None:
    """Stage 1 settings expose typed runtime and production references."""
    settings = AppSettings(
        _env_file=None,
        database_url=DATABASE_URL,
        design_production_rate_jph=60,
        illustrative_actual_production_rate_jph=46,
        app_port=9000,
    )
    assert settings.design_production_rate_jph == 60
    assert settings.illustrative_actual_production_rate_jph == 46
    assert settings.app_port == 9000

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, database_url=DATABASE_URL, app_port=0)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, database_url=DATABASE_URL, log_level="verbose")


def test_missing_database_configuration_is_reported_when_database_is_needed(monkeypatch) -> None:
    """The liveness app can start, while database operations explain missing configuration."""
    settings = AppSettings(_env_file=None)
    monkeypatch.setattr("bottleneck_analyzer.db.session.get_settings", lambda: settings)
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        settings.require_database_url()
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        create_db_engine()


def test_engine_and_session_are_configured_without_connection() -> None:
    """SQLAlchemy uses psycopg and can build sessions before a database exists."""
    engine = create_db_engine(DATABASE_URL)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        # Stage 2 registers business metadata; constructing an engine still performs no I/O.
        assert Base.metadata is not None
        assert engine.pool.checkedout() == 0
        factory = create_session_factory(engine)
        with factory() as session:
            assert session.bind is engine
    finally:
        engine.dispose()


def test_health_endpoints_report_liveness_and_missing_database_configuration(monkeypatch) -> None:
    """Health is available without a live database and does not claim connectivity."""
    settings = AppSettings(_env_file=None)
    monkeypatch.setattr("bottleneck_analyzer.main.get_settings", lambda: settings)
    monkeypatch.setattr("bottleneck_analyzer.db.session.get_settings", lambda: settings)
    with TestClient(app) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

        database_response = client.get("/health/database")
        assert database_response.status_code == 200
        assert database_response.json()["status"] == "misconfigured"
        assert database_response.json()["database_connected"] is False
        assert database_response.json()["vector_operations_available"] is False


def test_foundational_contracts_validate_scope_evidence_scenario_and_state() -> None:
    """Shared contracts reject invalid periods and preserve future workflow state."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    scope = AnalysisScope(start_time=start, end_time=start + timedelta(hours=8), shift="shift_1")
    evidence = EvidenceReference(
        evidence_id="E-1",
        source_type="shift_note",
        source_id="NOTE-1",
        relationship=EvidenceRelationship.DIRECT,
    )
    scenario = ScenarioRequest(
        target_station="Hemming",
        method=InterventionMethod.REPAIR_DURATION,
        reduction_percentage=30,
    )
    state = InvestigationState(
        question="Which station limits JPH?",
        intent=QuestionIntent.CONSTRAINT_OUTPUT_LOSS,
        scope=scope,
        retrieved_evidence=[evidence],
    )
    assert scenario.reduction_percentage == 30
    assert state.scope.shift == "shift_1"
    assert state.investigation_id

    with pytest.raises(ValidationError):
        AnalysisScope(start_time=start, end_time=start)
    with pytest.raises(ValidationError):
        ScenarioRequest(target_station="Hemming", reduction_percentage=0)
