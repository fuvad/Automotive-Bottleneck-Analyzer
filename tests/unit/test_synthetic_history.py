"""Pure Stage 2 checks; these tests never open a database connection."""

import json
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bottleneck_analyzer.data.connectors.mock import read_source_file
from bottleneck_analyzer.data.generators.cli import export_history
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.validation import DatasetValidationError, validate_history
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES, DatasetConfig


def small_config(**overrides) -> DatasetConfig:
    return DatasetConfig(
        **{"name": "unit-fixture", "days": 1, "vehicles_per_shift": 8, **overrides}
    )


def test_fixed_seed_is_repeatable_and_different_seed_changes_values() -> None:
    left = generate_history(small_config())
    right = generate_history(small_config())
    changed = generate_history(small_config(seed=21))
    assert left.rows == right.rows
    assert left.fingerprint() == right.fingerprint()
    assert left.fingerprint() != changed.fingerprint()


def test_configurable_dates_volume_models_shifts_and_station_order() -> None:
    config = small_config(
        days=2, vehicles_per_shift=5, start_time=datetime(2026, 10, 1, tzinfo=UTC)
    )
    history = generate_history(config)
    assert validate_history(history)["valid"]
    assert [r["name"] for r in history.rows["station"]] == list(STATION_NAMES)
    assert len(history.rows["shift"]) == 4
    assert len(history.rows["vehicle"]) == 20
    assert len(history.rows["production_record"]) == 140
    assert len(history.rows["buffer"]) == 6
    assert {r["name"] for r in history.rows["vehicle_model"]} == {"SUV", "Sedan"}
    assert config.end_time == config.start_time + timedelta(days=2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("days", 0),
        ("vehicles_per_shift", 0),
        ("name", "../escape"),
        ("start_time", "2026-09-01T00:00:00"),
        ("fault_focus", "Unknown"),
    ],
)
def test_invalid_configuration_is_rejected(field, value) -> None:
    with pytest.raises(ValidationError):
        small_config(**{field: value})


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_key",
        "negative_interval",
        "missing_required",
        "category",
        "quality",
        "duplicate_id",
        "outside_period",
        "station_sequence",
        "inferred_basis",
        "state_overlap",
        "naive_time",
    ],
)
def test_invalid_records_are_reported(mutation) -> None:
    history = deepcopy(generate_history(small_config()))
    if mutation == "foreign_key":
        history.rows["andon_event"][0]["fault_id"] = uuid4()
    elif mutation == "negative_interval":
        history.rows["station_event"][0]["end_time"] = history.config.start_time
    elif mutation == "missing_required":
        history.rows["vehicle"][0].pop("model_id")
    elif mutation == "category":
        history.rows["fault_event"][0]["category"] = "invented"
    elif mutation == "quality":
        history.rows["historian_observation"][0]["quality"] = "good"
        history.rows["historian_observation"][0]["value"] = None
    elif mutation == "duplicate_id":
        history.rows["vehicle"].append(history.rows["vehicle"][0].copy())
    elif mutation == "outside_period":
        history.rows["production_record"][0]["completed_at"] = history.config.end_time + timedelta(
            1
        )
    elif mutation == "station_sequence":
        history.rows["station"][0]["sequence"] = 7
    elif mutation == "inferred_basis":
        history.rows["evidence_link"][0]["basis"] = ""
    elif mutation == "state_overlap":
        history.rows["station_event"][0]["end_time"] += timedelta(seconds=1)
    elif mutation == "naive_time":
        history.rows["station_event"][0]["start_time"] = datetime(2026, 9, 1)
    with pytest.raises(DatasetValidationError):
        validate_history(history)


def test_source_imperfections_are_preserved() -> None:
    history = generate_history(small_config())
    assert {r["quality"] for r in history.rows["historian_observation"]} == {
        "good",
        "bad",
        "missing",
    }
    assert {r["relationship"] for r in history.rows["evidence_link"]} == {"direct", "inferred"}
    assert any(r["fault_id"] is None for r in history.rows["shift_handover_note"])
    assert len(history.rows["maintenance_work_order"]) < len(history.rows["fault_event"])
    assert len(history.rows["andon_event"]) < len(history.rows["fault_event"])
    assert all(r["raw"] for r in history.rows["source_record"])
    assert all(r["embedding"] is None for r in history.rows["source_record"])
    assert any("Canteen" in r["text"] for r in history.rows["shift_handover_note"])


def test_production_traversals_do_not_overlap_and_respect_planned_breaks() -> None:
    history = generate_history(small_config(vehicles_per_shift=345))
    shifts = {r["id"]: r for r in history.rows["shift"]}
    by_station = defaultdict(list)
    for row in history.rows["production_record"]:
        by_station[(row["station_id"], row["shift_id"])].append(row)
        shift_start = shifts[row["shift_id"]]["start_time"]
        assert not (
            row["started_at"] < shift_start + timedelta(hours=4, minutes=30)
            and row["completed_at"] > shift_start + timedelta(hours=4)
        )
    for group in by_station.values():
        ordered = sorted(group, key=lambda r: r["started_at"])
        assert all(a["completed_at"] <= b["started_at"] for a, b in zip(ordered, ordered[1:]))
    assert validate_history(history)["valid"]


def test_export_and_read_only_file_connectors(tmp_path) -> None:
    history = generate_history(small_config())
    destination = tmp_path / "dataset"
    manifest = export_history(history, destination)
    assert json.loads(manifest.read_text())["fingerprint"] == history.fingerprint()
    assert export_history(history, destination) == manifest
    assert len(list(read_source_file(destination / "MES.csv"))) == 112
    assert len(list(read_source_file(destination / "SCADA.jsonl"))) == 98
    assert len(list(destination.glob("SOP-*.txt"))) == 7
    with pytest.raises(ValueError, match="different"):
        export_history(generate_history(small_config(seed=3)), destination)


def test_framing_evidence_fixture_has_measured_fault_duration_difference() -> None:
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/framing_history.json").read_text())
    fixture.pop("expectation")
    history = generate_history(DatasetConfig(**fixture))
    durations = defaultdict(float)
    names = {r["id"]: r["name"] for r in history.rows["station"]}
    for fault in history.rows["fault_event"]:
        durations[names[fault["station_id"]]] += (
            fault["end_time"] - fault["start_time"]
        ).total_seconds()
    assert max(durations, key=durations.get) == "Framing"
    assert validate_history(history)["valid"]
