"""Opt-in PostgreSQL analytics: isolated fixtures and read-only persisted references."""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select, text, update

from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.analytics.service import analyze, analyze_connection
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.db.models.production import Dataset, SimulationRun, StationEvent
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.domain.manufacturing import DatasetConfig
from bottleneck_analyzer.simulation.config import SimulationConfig
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.persistence import persist_result

from .test_business_schema import schema_connection as schema_connection


@pytest.fixture
def analytics_fixture(schema_connection):
    history = generate_history(
        DatasetConfig(name="analytics-reference", days=1, vehicles_per_shift=6)
    )
    load_history(schema_connection, history)
    sim = run_simulation(
        SimulationConfig(name="analytics-sim", days=1, sop_reference_dataset="analytics-reference")
    )
    persist_result(schema_connection, sim)
    return schema_connection, sim


def assert_reference(result, metrics):
    line = result.overall.line
    assert line.admitted == metrics["released"]
    assert line.completed == metrics["completed"]
    assert line.final_wip == metrics["final_wip"]
    assert line.scheduled_hours == pytest.approx(metrics["scheduled_hours"])
    assert line.jph == pytest.approx(metrics["jph"])
    assert line.average_flow_seconds == pytest.approx(metrics["average_flow_seconds"], abs=0.001)
    assert line.average_wip == pytest.approx(metrics["average_wip"], abs=0.001)
    shifts = sorted((s for s in result.segments if s.kind == "shift"), key=lambda s: s.start_time)
    for index, shift in enumerate(shifts):
        expected = metrics["by_shift"][f"{index // 2}/shift_{index % 2 + 1}"]
        assert shift.line.completed == expected["completed"]
        assert shift.line.scheduled_hours == pytest.approx(expected["scheduled_hours"])
    for segment in result.segments:
        if segment.kind == "utc_hour":
            expected = [v for k, v in metrics["by_hour"].items() if int(k) % 24 == segment.utc_hour]
            assert segment.line.completed == sum(v["completed"] for v in expected)
            assert segment.line.scheduled_hours == pytest.approx(
                sum(v["scheduled_hours"] for v in expected)
            )
    for station, expected in zip(result.overall.stations, metrics["stations"], strict=True):
        assert station.operations == expected["operations"]
        for actual, name in [
            (station.processing_seconds, "processing_seconds"),
            (station.faulted_seconds, "fault_seconds"),
            (station.blocked_seconds, "blocked_seconds"),
            (station.starved_seconds, "starved_seconds"),
        ]:
            assert actual == pytest.approx(expected[name], abs=0.001)
        assert station.planned_closure_seconds == pytest.approx(expected["planned_closed_seconds"])
        assert station.average_input_queue == pytest.approx(
            expected["average_input_queue"], abs=0.001
        )
        assert station.maximum_input_queue <= expected["maximum_input_queue"]


def test_metrics_segments_provenance_isolation_and_replay(analytics_fixture):
    connection, sim = analytics_fixture
    scope = AnalyticsScope(dataset="analytics-sim")
    result = analyze_connection(connection, scope)
    assert_reference(result, sim.metrics)
    assert result.provenance == "simulation"
    assert len(result.overall.stations) == 7
    assert (
        sum(s.line.completed for s in result.segments if s.kind == "model")
        == sim.metrics["completed"]
    )
    assert sum(s.line.jph for s in result.segments if s.kind == "model") == result.overall.line.jph
    assert (
        sum(s.line.completed for s in result.segments if s.kind == "shift")
        == sim.metrics["completed"]
    )
    assert (
        sum(s.line.completed for s in result.segments if s.kind == "utc_hour")
        == sim.metrics["completed"]
    )
    assert all(
        s.line.jph is None for s in result.segments if s.utc_hour is not None and s.utc_hour >= 16
    )
    assert all(
        s.utilization is None
        for segment in result.segments
        if segment.kind == "model"
        for s in segment.stations
    )
    assert result == analyze_connection(connection, scope)
    authored = analyze_connection(connection, AnalyticsScope(dataset="analytics-reference"))
    assert authored.overall.line.completed == 12
    assert authored.provenance == "authored_fixture"
    assert all(s.average_input_queue is None for s in authored.overall.stations)
    for station in result.overall.stations:
        for reference in station.references:
            assert reference.dataset_id == result.dataset_id
            for source in reference.samples:
                assert source.source_id and source.source_type in {"MES", "SCADA"}
    with pytest.raises(ValueError, match="does not exist"):
        analyze_connection(connection, AnalyticsScope(dataset="missing"))


def test_partial_break_and_dated_shift_filters(analytics_fixture):
    connection, sim = analytics_fixture
    start = sim.config.start_time
    result = analyze_connection(
        connection,
        AnalyticsScope(
            dataset="analytics-sim",
            start_time=start + timedelta(hours=3.75),
            end_time=start + timedelta(hours=4.25),
        ),
    )
    assert result.overall.line.scheduled_hours == 0.25
    assert result.overall.stations[0].planned_closure_seconds == 900
    closed = analyze_connection(
        connection,
        AnalyticsScope(
            dataset="analytics-sim",
            start_time=start + timedelta(hours=18),
            end_time=start + timedelta(hours=19),
        ),
    )
    assert closed.overall.line.jph is None
    assert closed.overall.leading_candidate is None


@pytest.mark.parametrize("delta,expected", [(10, "Overlapping"), (-10, "Incomplete")])
def test_state_overlap_and_missing_coverage_are_explicit(schema_connection, delta, expected):
    history = generate_history(
        DatasetConfig(name="invalid-state-fixture", days=1, vehicles_per_shift=6)
    )
    load_history(schema_connection, history)
    row = (
        schema_connection.execute(
            select(StationEvent.__table__)
            .where(StationEvent.state == "blocked")
            .order_by(StationEvent.start_time)
            .limit(1)
        )
        .mappings()
        .one()
    )
    schema_connection.execute(
        update(StationEvent)
        .where(StationEvent.id == row["id"])
        .values(end_time=row["end_time"] + timedelta(seconds=delta))
    )
    result = analyze_connection(schema_connection, AnalyticsScope(dataset=history.config.name))
    station = next(s for s in result.overall.stations if s.station_id == row["station_id"])
    assert any(expected in w for w in station.warnings)
    if delta > 0:
        assert station.processing_seconds is None
        assert station.overlap_seconds == pytest.approx(10)
    else:
        assert station.state_coverage < 1


@pytest.fixture
def live_engine():
    if os.getenv("STAGE2_TEST_POSTGRES") != "1":
        pytest.skip("Set STAGE2_TEST_POSTGRES=1 for live PostgreSQL analytics tests")
    engine = create_db_engine()
    yield engine
    engine.dispose()


def test_persisted_30day_metrics_match_stage3_and_queries_are_read_only(live_engine):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())

    event.listen(live_engine, "before_cursor_execute", record)
    try:
        result = analyze(live_engine, AnalyticsScope(dataset="sim-30day-baseline-v1"))
    finally:
        event.remove(live_engine, "before_cursor_execute", record)
    assert set(statements) <= {"SELECT", "WITH", "SET"}
    assert len(statements) < 25  # Bounded batch queries, independent of 60 dated shifts.
    with live_engine.connect() as c:
        reference = c.scalar(
            select(SimulationRun.results).where(SimulationRun.dataset_id == result.dataset_id)
        )
    assert_reference(result, reference["metrics"])
    assert result.overall.line.completed == 21096
    assert result.overall.line.design_gap_jph == pytest.approx(13.12)
    assert result.overall.leading_candidate == "Hemming"
    assert len([s for s in result.segments if s.kind == "shift"]) == 60
    assert len([s for s in result.segments if s.kind == "utc_hour"]) == 24


def test_persisted_framing_case_identifies_framing_without_most_fault_loss(live_engine):
    result = analyze(live_engine, AnalyticsScope(dataset="sim-framing-validation-v1"))
    assert result.overall.line.completed == 1716
    assert result.overall.leading_candidate == "Framing"
    assert max(result.overall.stations, key=lambda s: s.faulted_seconds).station == "Hemming"
    with live_engine.connect() as c:
        hashes = dict(c.execute(select(Dataset.name, Dataset.content_hash)).all())
        assert hashes["stage2-30day-v1"] == (
            "cdea3a7b8470b6e0e2779f8bea6e539cdf73789862dd2ee646ca48919c2d41f1"
        )
        assert (
            c.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'stage2_test_%'"))
            == 0
        )


def test_assessment_requires_matching_configuration(live_engine):
    comparison = Path("data/processed/stage3/paired-comparison.json")
    assessment = Path("data/processed/stage3/constraint-assessment.json")
    if not comparison.exists() or not assessment.exists():
        pytest.skip("Optional saved Stage 3 experiment artifacts are absent")
    # Narrow scope still labels this as full-configuration context, not segment proof.
    result = analyze(
        live_engine,
        AnalyticsScope(dataset="sim-30day-baseline-v1", utc_hours=[0]),
        comparison_path=comparison,
        assessment_path=assessment,
    )
    assert result.simulation_evidence[-1]["baseline_constraint"]["primary"] == "Hemming"
