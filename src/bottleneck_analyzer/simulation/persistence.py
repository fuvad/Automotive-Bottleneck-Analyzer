"""Projection of real simulation events into the existing Stage 2 business schema."""

import math
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.engine import Connection

from bottleneck_analyzer.data.generators.history import EventHistory
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.data.validation import DatasetValidationError
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.models.production import Buffer, Dataset, SOPDocument, Station
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES, FaultCategory, StationState
from bottleneck_analyzer.simulation.calendars import Calendar
from bottleneck_analyzer.simulation.config import SimulationConfig, updated
from bottleneck_analyzer.simulation.engine import SimulationResult
from bottleneck_analyzer.simulation.validation import validate_result


class SimulationHistory(EventHistory):
    provenance = "simulation"


def topology_from_dataset(connection: Connection, config: SimulationConfig) -> SimulationConfig:
    """Read station sequence, planned cycles, finite buffers and dated calendar from Stage 2."""
    source_id = connection.scalar(
        select(Dataset.id).where(Dataset.name == config.sop_reference_dataset)
    )
    if source_id is None:
        raise ValueError("The reference dataset does not exist")
    stations = (
        connection.execute(
            select(Station.__table__)
            .where(Station.dataset_id == source_id)
            .order_by(Station.sequence)
        )
        .mappings()
        .all()
    )
    if tuple(s["name"] for s in stations) != STATION_NAMES:
        raise ValueError("Reference dataset does not contain the expected station sequence")
    buffers = (
        connection.execute(select(Buffer.__table__).where(Buffer.dataset_id == source_id))
        .mappings()
        .all()
    )
    capacities = {r["upstream_station_id"]: r for r in buffers}
    if len(capacities) != 6 or any(
        capacities.get(a["id"], {}).get("downstream_station_id") != b["id"]
        for a, b in zip(stations, stations[1:])
    ):
        raise ValueError("Reference finite buffers do not connect consecutive stations")
    # Planned cycles remain the 60-JPH design reference. Distribution means are explicit
    # synthetic processing assumptions, not overwritten by an authored production count.
    from bottleneck_analyzer.db.models.production import CalendarExclusion, Shift

    shifts = (
        connection.execute(
            select(Shift.__table__)
            .where(Shift.dataset_id == source_id)
            .order_by(Shift.start_time)
            .limit(2)
        )
        .mappings()
        .all()
    )
    from bottleneck_analyzer.simulation.config import ShiftPattern

    patterns = []
    start_date = (
        shifts[0]["start_time"]
        .astimezone(config.start_time.tzinfo)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    for shift in shifts:
        breaks = (
            connection.execute(
                select(CalendarExclusion.__table__).where(CalendarExclusion.shift_id == shift["id"])
            )
            .mappings()
            .all()
        )
        if len(breaks) != 1:
            raise ValueError("This simulator currently supports one planned break per shift")
        patterns.append(
            ShiftPattern(
                name=shift["name"],
                start_seconds=(shift["start_time"] - start_date).total_seconds(),
                duration_seconds=(shift["end_time"] - shift["start_time"]).total_seconds(),
                break_start_seconds=(breaks[0]["start_time"] - shift["start_time"]).total_seconds(),
                break_seconds=(breaks[0]["end_time"] - breaks[0]["start_time"]).total_seconds(),
            )
        )
    return updated(
        config,
        shifts=tuple(patterns),
        buffer_capacities=tuple(capacities[s["id"]]["capacity"] for s in stations[:-1]),
    )


def project_result(result: SimulationResult) -> SimulationHistory:
    validate_result(result)
    config = result.config
    calendar = Calendar(config)
    history = SimulationHistory(config)

    def timestamp(seconds: float):
        return config.start_time + timedelta(seconds=seconds)

    stations = [
        history.add("station", name, name=name, sequence=i + 1, planned_cycle_seconds=60.0)
        for i, name in enumerate(STATION_NAMES)
    ]
    for i, capacity in enumerate(config.buffer_capacities):
        history.add(
            "buffer",
            str(i),
            upstream_station_id=stations[i],
            downstream_station_id=stations[i + 1],
            capacity=capacity,
        )
    models = {name: history.add("vehicle_model", name, name=name) for name in ("SUV", "Sedan")}
    shifts = {}
    for window in calendar.windows:
        key = (window.day, window.name)
        shifts[key] = history.add(
            "shift",
            f"{key[0]}/{key[1]}",
            name=window.name,
            start_time=timestamp(window.start),
            end_time=timestamp(window.end),
            timezone_name="UTC",
        )
        if window.break_end > window.break_start:
            history.add(
                "calendar_exclusion",
                f"{key[0]}/{key[1]}",
                shift_id=shifts[key],
                start_time=timestamp(window.break_start),
                end_time=timestamp(window.break_end),
                reason="planned_break",
            )

    def shift_id(time):
        window = calendar.shift_at(max(0, time - 1e-7))
        if window is None:
            raise ValueError("Event has no production shift")
        return shifts[(window.day, window.name)]

    operation_sources = defaultdict(list)
    for vehicle in result.vehicles:
        vehicle_id = history.add(
            "vehicle",
            str(vehicle.sequence),
            model_id=models[vehicle.model],
            release_sequence=vehicle.sequence,
            released_at=timestamp(vehicle.release),
        )
        for operation in vehicle.operations:
            if operation.end is None:
                continue  # Censored operation retained in simulation_run.results below.
            key = f"{vehicle.sequence}/{operation.station}"
            raw = {
                "vehicle_id": str(vehicle_id),
                "model": vehicle.model,
                "simulation": True,
                **asdict(operation),
                "release": vehicle.release,
                "completion": vehicle.completion,
                "waiting_wall_seconds": operation.start - operation.arrival,
                "blocked_wall_seconds": (operation.departure - operation.end)
                if operation.departure is not None
                else None,
            }
            source = history.source(
                "MES", key, timestamp(operation.end), stations[operation.station], raw
            )
            operation_sources[operation.station].append((operation.start, operation.end, source))
            history.add(
                "production_record",
                key,
                source_record_id=source,
                vehicle_id=vehicle_id,
                station_id=stations[operation.station],
                shift_id=shift_id(operation.end),
                started_at=timestamp(operation.start),
                completed_at=timestamp(operation.end),
            )

    fault_states = defaultdict(list)
    for index, state in enumerate(result.states):
        for window in calendar.windows[
            max(0, int(state.start // 86400)) * 2 : min(config.days, int(state.end // 86400) + 1)
            * 2
        ]:
            start, end = max(state.start, window.start), min(state.end, window.end)
            if end - start <= 1e-7:
                continue
            key = f"state/{index}/{window.day}/{window.name}"
            source = history.source(
                "SCADA",
                key,
                timestamp(start),
                stations[state.station],
                {
                    "state": state.state,
                    "start_seconds": start,
                    "end_seconds": end,
                    "simulation": True,
                },
            )
            event = history.add(
                "station_event",
                key,
                source_record_id=source,
                station_id=stations[state.station],
                shift_id=shifts[(window.day, window.name)],
                start_time=timestamp(start),
                end_time=timestamp(end),
                state=state.state,
            )
            if state.state == "faulted":
                fault_states[state.station].append((start, end, event, source))
    for station in fault_states:
        fault_states[station].sort()
    operation_starts = {}
    for station in operation_sources:
        operation_sources[station].sort()
        operation_starts[station] = [row[0] for row in operation_sources[station]]
    for index, fault in enumerate(result.faults):
        related = [
            s
            for s in fault_states[fault.station]
            if s[0] >= fault.start - 1e-6
            and s[1] <= fault.end + 1e-6
            and s[1] > fault.start
            and s[0] < fault.end
        ]
        if not related:
            raise ValueError("A physical fault has no active fault-state evidence")
        key = f"fault/{fault.station}/{fault.category}/{fault.equipment_id}/{fault.occurrence}"
        source = history.source(
            "SCADA",
            key,
            timestamp(fault.start),
            stations[fault.station],
            {
                **asdict(fault),
                "simulation": True,
                "scheduled_loss_seconds": calendar.scheduled_between(fault.start, fault.end),
            },
        )
        fault_id = history.add(
            "fault_event",
            key,
            source_record_id=source,
            station_id=stations[fault.station],
            station_event_id=related[0][2],
            category=fault.category,
            equipment_id=fault.equipment_id,
            fault_code=f"SIM-{fault.category}",
            start_time=timestamp(fault.start),
            end_time=timestamp(fault.end),
        )
        for _, _, _, state_source in related:
            history.link(
                source,
                state_source,
                "direct",
                "Same simulated physical failure; active repair fragment",
            )
        position = bisect_right(operation_starts.get(fault.station, []), fault.start) - 1
        if position >= 0:
            begin, end, production_source = operation_sources[fault.station][position]
            if begin <= fault.start < end:
                history.link(
                    production_source,
                    source,
                    "direct",
                    "This simulated station operation was interrupted by the same fault",
                )
        text = f"Simulated {fault.category} on {fault.equipment_id}; modeled repair recorded."
        if index % 4:
            work_source = history.source(
                "CMMS",
                key,
                timestamp(fault.start),
                stations[fault.station],
                {"fault_event_id": str(fault_id), "description": text, "simulation": True},
                text,
            )
            history.add(
                "maintenance_work_order",
                key,
                source_record_id=work_source,
                station_id=stations[fault.station],
                fault_id=fault_id,
                opened_at=timestamp(fault.start),
                closed_at=None if fault.truncated else timestamp(fault.end),
                status="open" if fault.truncated else "closed",
                description=text,
                recorded_cause=None,
            )
            history.link(source, work_source, "direct", "Explicit simulated fault_event_id")
        if index % 3:
            andon_source = history.source(
                "Andon",
                key,
                timestamp(fault.start),
                stations[fault.station],
                {"fault_event_id": str(fault_id), "remarks": text},
                text,
            )
            history.add(
                "andon_event",
                key,
                source_record_id=andon_source,
                station_id=stations[fault.station],
                fault_id=fault_id,
                called_at=timestamp(fault.start),
                remarks=text,
            )
            history.link(source, andon_source, "direct", "Explicit simulated incident reference")
        quality = ("good", "bad", "missing")[index % 3]
        value = 1.0 if quality == "good" else (-999.0 if quality == "bad" else None)
        sensor = history.source(
            "historian",
            key,
            timestamp(fault.start),
            stations[fault.station],
            {
                "fault_event_id": str(fault_id),
                "tag": "simulated_fault_active",
                "value": value,
                "quality": quality,
                "unit": "boolean",
            },
        )
        history.add(
            "historian_observation",
            key,
            source_record_id=sensor,
            station_id=stations[fault.station],
            fault_id=fault_id,
            observed_at=timestamp(fault.start),
            measurement_name="simulated_fault_active",
            value=value,
            quality=quality,
            unit="boolean",
        )
        history.link(
            source, sensor, "direct", "Same simulated fault-active indicator; not a physical cause"
        )
        if index % 5 == 0:
            note = "Simulated station interruption noted; incident identifier omitted."
            note_source = history.source(
                "shift_notes",
                key,
                timestamp(fault.start),
                stations[fault.station],
                {"note": note},
                note,
            )
            history.add(
                "shift_handover_note",
                key,
                source_record_id=note_source,
                station_id=stations[fault.station],
                fault_id=None,
                shift_id=shift_id(fault.start + 1e-6),
                recorded_at=timestamp(fault.start),
                text=note,
            )
            history.link(
                source, note_source, "inferred", "Station/time association; note has no incident ID"
            )
    # One unrelated note per shift exercises retrieval filtering without inventing causal links.
    for window in calendar.windows:
        key = f"unrelated/{window.day}/{window.name}"
        text = "Synthetic handover: canteen menu updated; no equipment observation."
        source = history.source(
            "shift_notes", key, timestamp(window.start), None, {"text": text}, text
        )
        history.add(
            "shift_handover_note",
            key,
            source_record_id=source,
            shift_id=shifts[(window.day, window.name)],
            station_id=None,
            fault_id=None,
            recorded_at=timestamp(window.start),
            text=text,
        )
    model = history.add(
        "model_configuration",
        config.version,
        version=config.version,
        parameters=config.model_dump(mode="json"),
        approved_by=None,
        approved_at=None,
    )
    history.add(
        "simulation_run",
        "baseline" if config.intervention is None else "intervention",
        configuration_id=model,
        seed=config.seed,
        parameters={
            "version": config.version,
            "config": config.model_dump(mode="json"),
            "role": "baseline" if config.intervention is None else "intervention",
        },
        results={
            "metrics": result.metrics,
            "censored_vehicles": [asdict(v) for v in result.vehicles if v.completion is None],
        },
        recorded_at=config.end_time,
    )
    return history


def validate_simulation_history(history: EventHistory) -> dict:
    """Simulation-aware schema validation: partial WIP and cross-shift operations are valid."""
    if history.provenance != "simulation":
        raise DatasetValidationError("Expected simulation provenance")
    indexes = {name: {row["id"]: row for row in rows} for name, rows in history.rows.items()}
    indexes["dataset"] = {history.dataset_id: {"id": history.dataset_id}}
    calendar = Calendar(history.config)
    for name, rows in history.rows.items():
        if len(indexes[name]) != len(rows):
            raise DatasetValidationError(f"Duplicate IDs in {name}")
        for row in rows:
            if row.get("dataset_id") != history.dataset_id:
                raise DatasetValidationError("Cross-dataset record")
            for column in Base.metadata.tables[name].columns:
                value = row.get(column.name)
                if isinstance(value, datetime) and (
                    value.utcoffset() is None
                    or not history.config.start_time <= value <= history.config.end_time
                ):
                    raise DatasetValidationError(f"Timestamp outside observation period: {name}")
                if isinstance(value, float) and not math.isfinite(value):
                    raise DatasetValidationError(f"Non-finite value: {name}.{column.name}")
                if not column.nullable and column.computed is None and value is None:
                    raise DatasetValidationError(f"Required value missing: {name}.{column.name}")
                for fk in column.foreign_keys:
                    if value is not None and value not in indexes.get(fk.column.table.name, {}):
                        raise DatasetValidationError(f"Invalid foreign key: {name}.{column.name}")
            for a, b in (
                ("start_time", "end_time"),
                ("started_at", "completed_at"),
                ("opened_at", "closed_at"),
            ):
                if row.get(a) is not None and row.get(b) is not None and row[b] <= row[a]:
                    raise DatasetValidationError(f"Invalid interval: {name}")
    if (
        tuple(r["name"] for r in sorted(history.rows["station"], key=lambda s: s["sequence"]))
        != STATION_NAMES
    ):
        raise DatasetValidationError("Wrong station ordering")
    runs = history.rows.get("simulation_run", [])
    if len(runs) != 1 or len(history.rows["vehicle"]) != runs[0]["results"]["metrics"]["released"]:
        raise DatasetValidationError("Simulation-run vehicle accounting differs")
    final_station = history.rows["station"][-1]["id"]
    completions = sum(
        r["station_id"] == final_station for r in history.rows.get("production_record", [])
    )
    if completions != runs[0]["results"]["metrics"]["completed"]:
        raise DatasetValidationError("Final Inspection count differs from simulation")
    metrics = runs[0]["results"]["metrics"]
    if not math.isclose(metrics["scheduled_hours"], calendar.scheduled_seconds / 3600):
        raise DatasetValidationError("Stored calendar denominator differs from the configuration")
    if not math.isclose(metrics["jph"], completions / metrics["scheduled_hours"]):
        raise DatasetValidationError("Stored JPH differs from Final Inspection count")
    groups = defaultdict(list)
    for state in history.rows["station_event"]:
        if state["state"] not in set(StationState):
            raise DatasetValidationError("Invalid station state")
        groups[(state["station_id"], state["shift_id"])].append(state)
    if len(groups) != 7 * len(history.rows["shift"]):
        raise DatasetValidationError("Missing station/shift state history")
    for (_, shift_id), states in groups.items():
        shift = indexes["shift"][shift_id]
        states.sort(key=lambda r: r["start_time"])
        if (
            states[0]["start_time"] != shift["start_time"]
            or states[-1]["end_time"] != shift["end_time"]
        ):
            raise DatasetValidationError("Station/shift state coverage is incomplete")
        if any(a["end_time"] != b["start_time"] for a, b in zip(states, states[1:])):
            raise DatasetValidationError("Station state intervals overlap or leave gaps")
    for fault in history.rows.get("fault_event", []):
        if fault["category"] not in set(FaultCategory):
            raise DatasetValidationError("Unknown fault category")
        state = indexes["station_event"][fault["station_event_id"]]
        if (
            state["state"] != "faulted"
            or state["station_id"] != fault["station_id"]
            or state["start_time"] < fault["start_time"]
            or state["end_time"] > fault["end_time"]
        ):
            raise DatasetValidationError("Physical fault and active repair fragment disagree")
    routes = defaultdict(list)
    station_sequences = {r["id"]: r["sequence"] for r in history.rows["station"]}
    for operation in history.rows.get("production_record", []):
        routes[operation["vehicle_id"]].append(operation)
    for operations in routes.values():
        operations.sort(key=lambda r: station_sequences[r["station_id"]])
        if [station_sequences[o["station_id"]] for o in operations] != list(
            range(1, len(operations) + 1)
        ):
            raise DatasetValidationError(
                "Persisted vehicle route is not a prefix of the seven stations"
            )
        if any(a["completed_at"] > b["started_at"] for a, b in zip(operations, operations[1:])):
            raise DatasetValidationError("Persisted vehicle operations overlap")
    return {"valid": True, "provenance": "simulation", "counts": history.counts()}


def persist_result(connection: Connection, result: SimulationResult) -> dict:
    # Reuse existing SOPs by dataset/version reference in configuration, not by copying content.
    sop_count = connection.execute(
        select(SOPDocument.id)
        .join(Dataset, Dataset.id == SOPDocument.dataset_id)
        .where(Dataset.name == result.config.sop_reference_dataset)
    ).all()
    if not sop_count:
        raise DatasetValidationError(
            "Referenced SOP dataset is unavailable; it will not be recreated"
        )
    history = project_result(result)
    return load_history(connection, history, validator=validate_simulation_history)
