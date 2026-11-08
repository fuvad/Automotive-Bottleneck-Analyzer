"""Hand-checked interval, denominator and candidate tests; no database required."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bottleneck_analyzer.analytics.calendar import (
    build_segments,
    hourly,
    intersect,
    merge,
    seconds,
    subtract,
)
from bottleneck_analyzer.analytics.candidates import leader, rank_candidates, ratio
from bottleneck_analyzer.analytics.contracts import AnalyticsScope, StationMetrics
from bottleneck_analyzer.analytics.service import load_assessment

ORIGIN = datetime(2026, 9, 1, tzinfo=UTC)


def t(hours):
    return ORIGIN + timedelta(hours=hours)


@pytest.mark.parametrize(
    "value,denominator,expected", [(345, 7.5, 46), (0, 1, 0), (3, 0, None), (None, 2, None)]
)
def test_jph_and_zero_denominator(value, denominator, expected):
    assert ratio(value, denominator) == expected
    if expected == 46:
        assert 60 - expected == 14


def test_calendar_merges_overlap_and_subtracts_break_union():
    shifts = [(t(0), t(8)), (t(8), t(16))]
    breaks = [(t(4), t(4.5)), (t(4.25), t(4.5)), (t(12), t(12.5))]
    scheduled = subtract(shifts, breaks)
    assert seconds(scheduled) == 15 * 3600
    assert seconds(intersect(scheduled, [(t(3.75), t(4.25))])) == 900
    assert merge([(t(1), t(2)), (t(0), t(1))]) == [(t(0), t(2))]


def test_hour_boundaries_partial_and_closed_hours():
    windows = [(t(3.5), t(5.25))]
    assert seconds(hourly(windows, [3])) == 1800
    assert seconds(hourly(windows, [4])) == 3600
    assert seconds(hourly(windows, [5])) == 900
    assert hourly(windows, [18]) == []


def test_shift_model_and_hour_segments_use_dated_calendar():
    shift_id = uuid4()
    dataset = {"start_time": t(0), "end_time": t(24)}
    shifts = [{"id": shift_id, "name": "shift_1", "start_time": t(0), "end_time": t(8)}]
    breaks = [{"start_time": t(4), "end_time": t(4.5)}]
    segments = build_segments(dataset, shifts, breaks, AnalyticsScope(dataset="test"))
    assert seconds(segments[0].scheduled) == 7.5 * 3600
    assert len([s for s in segments if s.kind == "shift"]) == 1
    assert {s.model for s in segments if s.kind == "model"} == {"SUV", "Sedan"}
    assert seconds(next(s for s in segments if s.utc_hour == 4).scheduled) == 1800
    assert seconds(next(s for s in segments if s.utc_hour == 18).scheduled) == 0
    filtered = build_segments(
        dataset, shifts, breaks, AnalyticsScope(dataset="test", shift_id=shift_id, utc_hours=[4])
    )
    assert seconds(filtered[0].scheduled) == 1800
    with pytest.raises(ValueError, match="does not belong"):
        build_segments(dataset, shifts, breaks, AnalyticsScope(dataset="test", shift_id=uuid4()))


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_time": "2026-09-01T00:00:00"},
        {"utc_hours": [24]},
        {"utc_hours": [1, 1]},
        {"station": "Unknown"},
        {"model": "Truck"},
        {"time_of_day": "morning"},
        {"start_time": t(2), "end_time": t(1)},
    ],
)
def test_scope_rejects_invalid_or_ambiguous_filters(overrides):
    with pytest.raises(ValidationError):
        AnalyticsScope(dataset="test", **overrides)


def metric(name, sequence, **updates):
    return StationMetrics(
        **{
            "station_id": uuid4(),
            "station": name,
            "sequence": sequence,
            "operations": 100,
            "scheduled_seconds": 7200,
            "processing_seconds": 4000,
            "utilization": 4000 / 7200,
            "faulted_seconds": 0,
            "blocked_seconds": 0,
            "starved_seconds": 0,
            "state_coverage": 1,
            "overlap_seconds": 0,
            "mean_service_seconds": 40,
            "average_input_queue": 0,
            "input_capacity": 5,
            "queue_basis": "fixture",
            **updates,
        }
    )


def test_ranking_uses_propagation_not_highest_downtime_and_keeps_conflicts():
    stations = [
        metric("Underbody Welding", 1, blocked_seconds=1800),
        metric("Framing", 2, processing_seconds=6500, average_input_queue=4.5),
        metric("Roof Welding", 3, starved_seconds=1800),
        metric("Hemming", 5, faulted_seconds=3000, blocked_seconds=1500),
    ]
    ranked = rank_candidates(stations)
    assert leader(ranked) == "Framing"
    assert ranked[0].strength == "strong"
    hemming = next(c for c in ranked if c.station == "Hemming")
    assert any("downstream restriction" in e for e in hemming.contradicting_evidence)
    assert ranked == rank_candidates(stations)


def test_insufficient_samples_missing_coverage_overlap_and_ties():
    for updates in ({"operations": 2}, {"state_coverage": 0.4}, {"overlap_seconds": 4}):
        candidates = rank_candidates([metric("Framing", 2, **updates)])
        assert candidates[0].strength == "insufficient_evidence"
        assert leader(candidates) is None
    candidates = rank_candidates([metric("A", 1), metric("B", 3)])
    assert leader(candidates) is None


def test_model_evidence_never_claims_shared_utilization_or_strong_confidence():
    candidates = rank_candidates(
        [
            metric("Framing", 2, mean_service_seconds=90, average_input_queue=4),
            metric("Roof Welding", 3, mean_waiting_wall_seconds=900),
        ],
        model_segment=True,
    )
    assert candidates[0].strength != "strong"
    assert any("Shared machine states" in e for e in candidates[0].contradicting_evidence)


def test_simulation_report_association_rejects_mismatch(tmp_path):
    import json

    config = {"name": "example", "seed": 1, "days": 30}
    dataset = {"id": uuid4(), "config": config}
    comparison, assessment = tmp_path / "comparison.json", tmp_path / "assessment.json"
    comparison.write_text(json.dumps({"baseline_config": config, "baseline": {"mean": 46}}))
    assessment.write_text(json.dumps({"baseline": {"mean": 46}, "baseline_constraint": {}}))
    assert (
        load_assessment(dataset, comparison, assessment)["type"]
        == "separate_simulation_sensitivity"
    )
    with pytest.raises(ValueError, match="both"):
        load_assessment(dataset, comparison, None)
    with pytest.raises(ValueError, match="configuration"):
        load_assessment({**dataset, "config": {**config, "days": 3}}, comparison, assessment)
    assessment.write_text(json.dumps({"baseline": {"mean": 47}, "baseline_constraint": {}}))
    with pytest.raises(ValueError, match="summary"):
        load_assessment(dataset, comparison, assessment)
