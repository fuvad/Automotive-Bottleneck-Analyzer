"""Dataset integrity checks independent of source generation and persistence."""

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from bottleneck_analyzer.data.generators.history import EventHistory
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.models import production  # noqa: F401
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES, FaultCategory, StationState


class DatasetValidationError(ValueError):
    """One or more explicit integrity failures in a dataset."""


def validate_history(history: EventHistory) -> dict[str, Any]:
    """Reject malformed records and links; retain explicitly flagged bad readings."""
    issues: list[str] = []
    config = history.config
    dataset_id = history.dataset_id
    indexes = {name: {row["id"]: row for row in rows} for name, rows in history.rows.items()}
    indexes["dataset"] = {dataset_id: {"id": dataset_id}}
    for name, rows in history.rows.items():
        table = Base.metadata.tables[name]
        if len(indexes[name]) != len(rows):
            issues.append(f"{name}: duplicate identifiers")
        for row in rows:
            if row.get("dataset_id") != dataset_id:
                issues.append(f"{name}: wrong dataset namespace")
            for column in table.columns:
                value = row.get(column.name)
                if not column.nullable and column.computed is None and value is None:
                    issues.append(f"{name}.{column.name}: required field is missing")
                if isinstance(value, datetime):
                    if value.utcoffset() is None:
                        issues.append(f"{name}.{column.name}: timezone is missing")
                    elif not config.start_time <= value <= config.end_time:
                        issues.append(f"{name}.{column.name}: outside dataset period")
                if isinstance(value, float) and not math.isfinite(value):
                    issues.append(f"{name}.{column.name}: non-finite number")
                for foreign_key in column.foreign_keys:
                    if value is not None and value not in indexes.get(
                        foreign_key.column.table.name, {}
                    ):
                        issues.append(f"{name}.{column.name}: foreign key does not exist")
            for begin, end in (
                ("start_time", "end_time"),
                ("started_at", "completed_at"),
                ("opened_at", "closed_at"),
            ):
                if row.get(begin) is not None and row.get(end) is not None:
                    try:
                        if row[end] <= row[begin]:
                            issues.append(f"{name}: invalid interval")
                    except TypeError:
                        issues.append(f"{name}: incompatible timestamp timezones")
    if issues:
        raise DatasetValidationError("; ".join(sorted(set(issues))))
    station_rows = sorted(history.rows.get("station", []), key=lambda row: row["sequence"])
    if [(r["name"], r["sequence"]) for r in station_rows] != list(
        zip(STATION_NAMES, range(1, 8), strict=True)
    ):
        issues.append("station: expected exactly seven ordered stations")
    station_sequence = {r["id"]: r["sequence"] for r in station_rows}
    buffers = history.rows.get("buffer", [])
    if len(buffers) != 6 or any(
        r["capacity"] <= 0
        or station_sequence.get(r["downstream_station_id"], -1)
        != station_sequence.get(r["upstream_station_id"], -1) + 1
        for r in buffers
    ):
        issues.append("buffer: expected six sequential finite buffers")
    if {r["name"] for r in history.rows.get("vehicle_model", [])} != {"SUV", "Sedan"}:
        issues.append("vehicle_model: both models are required")
    shifts = history.rows.get("shift", [])
    if len(shifts) != config.days * 2 or {r["name"] for r in shifts} != {"shift_1", "shift_2"}:
        issues.append("shift: expected two dated shifts per day")
    if {r["model_id"] for r in history.rows.get("vehicle", [])} != set(
        indexes.get("vehicle_model", {})
    ):
        issues.append("vehicle: both models must be represented")

    states: dict[tuple, list] = defaultdict(list)
    for event in history.rows.get("station_event", []):
        if event["state"] not in set(StationState):
            issues.append("station_event: invalid state")
        states[(event["station_id"], event["shift_id"])].append(event)
    for group in states.values():
        group.sort(key=lambda row: row["start_time"])
        shift = indexes.get("shift", {}).get(group[0]["shift_id"])
        if shift and (
            group[0]["start_time"] != shift["start_time"]
            or group[-1]["end_time"] != shift["end_time"]
            or any(a["end_time"] != b["start_time"] for a, b in zip(group, group[1:]))
        ):
            issues.append("station_event: overlapping or incomplete state intervals")
    for fault in history.rows.get("fault_event", []):
        if fault["category"] not in set(FaultCategory):
            issues.append("fault_event: invalid category")
        event = indexes.get("station_event", {}).get(fault["station_event_id"])
        if event and (
            event["state"] != "faulted"
            or event["station_id"] != fault["station_id"]
            or event["start_time"] != fault["start_time"]
            or event["end_time"] != fault["end_time"]
        ):
            issues.append("fault_event: inconsistent linked state interval")
    for table in (
        "maintenance_work_order",
        "andon_event",
        "shift_handover_note",
        "historian_observation",
    ):
        for row in history.rows.get(table, []):
            fault = indexes.get("fault_event", {}).get(row.get("fault_id"))
            if fault and fault["station_id"] != row["station_id"]:
                issues.append(f"{table}: fault and station disagree")
    for row in history.rows.get("evidence_link", []):
        if row["relationship"] not in {"direct", "inferred"} or not row["basis"].strip():
            issues.append("evidence_link: invalid relationship or missing basis")
    for row in history.rows.get("historian_observation", []):
        if row["quality"] not in {"good", "bad", "missing"}:
            issues.append("historian: invalid quality")
        if row["quality"] == "good" and row["value"] is None:
            issues.append("historian: good reading requires a value")

    routes: dict[Any, list] = defaultdict(list)
    for row in history.rows.get("production_record", []):
        routes[row["vehicle_id"]].append(row)
        shift = indexes.get("shift", {}).get(row["shift_id"])
        if shift and not (
            shift["start_time"] <= row["started_at"] < row["completed_at"] <= shift["end_time"]
        ):
            issues.append("production_record: outside its shift")
    if len(routes) != len(history.rows.get("vehicle", [])):
        issues.append("production_record: missing vehicle history")
    for route in routes.values():
        route.sort(key=lambda row: station_sequence.get(row["station_id"], 0))
        if len(route) != 7 or {r["station_id"] for r in route} != set(station_sequence):
            issues.append("production_record: incomplete seven-station route")
        if any(a["completed_at"] > b["started_at"] for a, b in zip(route, route[1:])):
            issues.append("production_record: vehicle overlaps successive stations")
    if issues:
        raise DatasetValidationError("; ".join(sorted(set(issues))))
    return {
        "valid": True,
        "counts": history.counts(),
        "provenance": "authored_fixture",
        "warnings": ["Not simulation-derived; no bottleneck or gain has been validated."],
    }
