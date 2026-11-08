"""Authored event fixtures used to verify the source pipeline before Stage 3.

This module does not simulate the line or identify a bottleneck. All fixture
timings and the requested production volume are inputs, not model predictions.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, ClassVar, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from bottleneck_analyzer.domain.manufacturing import STATION_NAMES, DatasetConfig

type Row = dict[str, Any]


class HistoryConfiguration(Protocol):
    name: str
    seed: int
    days: int
    start_time: datetime

    @property
    def end_time(self) -> datetime: ...

    def model_dump(self, **kwargs) -> dict: ...

    def model_dump_json(self) -> str: ...


@dataclass
class EventHistory:
    config: HistoryConfiguration
    rows: dict[str, list[Row]] = field(default_factory=dict)
    provenance: ClassVar[str] = "authored_fixture"

    @property
    def dataset_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"bottleneck-analyzer/dataset/{self.config.name}")

    def identifier(self, key: str) -> UUID:
        return uuid5(self.dataset_id, key)

    def add(self, table: str, key: str, **values: Any) -> UUID:
        identifier = self.identifier(f"{table}/{key}")
        self.rows.setdefault(table, []).append(
            {"id": identifier, "dataset_id": self.dataset_id, **values}
        )
        return identifier

    def source(
        self,
        system: str,
        key: str,
        when: datetime,
        station: UUID | None,
        original: Row,
        text: str = "",
    ) -> UUID:
        suffix = "csv" if system in {"MES", "historian"} else "jsonl"
        return self.add(
            "source_record",
            f"{system}/{key}",
            system=system,
            source_id=key,
            recorded_at=when,
            station_id=station,
            raw=original,
            text_content=text,
            original_path=f"data/raw/{self.config.name}/{system}.{suffix}",
            embedding=None,
            embedding_model=None,
        )

    def link(self, left: UUID, right: UUID, relationship: str, basis: str) -> None:
        self.add(
            "evidence_link",
            f"{left}/{right}",
            from_record_id=left,
            to_record_id=right,
            relationship=relationship,
            basis=basis,
        )

    def fingerprint(self) -> str:
        """Hash every normalized field and original value in a stable order."""
        digest = hashlib.sha256(self.config.model_dump_json().encode())
        for table in sorted(self.rows):
            for row in self.rows[table]:
                digest.update(table.encode())
                digest.update(json.dumps(row, default=str, sort_keys=True).encode())
        return digest.hexdigest()

    def counts(self) -> dict[str, int]:
        return {table: len(rows) for table, rows in sorted(self.rows.items())}


def _supporting_records(
    history: EventHistory,
    rng: random.Random,
    key: str,
    station: UUID,
    station_name: str,
    shift: UUID,
    start: datetime,
    end: datetime,
    fault: UUID,
    fault_source: UUID,
    number: int,
) -> None:
    """Derive imperfect human/sensor source records from one shared incident."""
    if number % 4 != 0:
        opened = end + timedelta(minutes=rng.randint(10, 60))
        text = rng.choice(
            [
                "Robot stopped; inspected connector and acknowledged maintenance request.",
                "Intermittent servo alarm. Technician recorded connector inspection.",
                "Robot trip; connector reseated. Follow-up inspection required.",
            ]
        )
        source = history.source(
            "CMMS",
            key,
            opened,
            station,
            {"fault_event_id": str(fault), "description": text},
            text,
        )
        closed = None if number % 7 == 0 else opened + timedelta(minutes=20)
        history.add(
            "maintenance_work_order",
            key,
            source_record_id=source,
            station_id=station,
            fault_id=fault,
            opened_at=opened,
            closed_at=closed,
            description=text,
            status="open" if closed is None else "closed",
            recorded_cause=None if number % 3 else "loose connector reported by technician",
        )
        history.link(fault_source, source, "direct", "Shared explicit fault_event_id")
    if number % 3 != 0:
        when = start + timedelta(seconds=10)
        text = f"{station_name}: robot alarm; operator requests maintenance assistance."
        source = history.source(
            "Andon",
            key,
            when,
            station,
            {"incident": str(fault), "remarks": text},
            text,
        )
        history.add(
            "andon_event",
            key,
            source_record_id=source,
            station_id=station,
            fault_id=fault,
            called_at=when,
            remarks=text,
        )
        history.link(fault_source, source, "direct", "Explicit incident identifier")
    if number % 5 == 0:
        when = end + timedelta(hours=2)
        text = "Robot interruption earlier; inspect during next approved maintenance window."
        source = history.source("shift_notes", key, when, station, {"note": text}, text)
        history.add(
            "shift_handover_note",
            key,
            source_record_id=source,
            shift_id=shift,
            station_id=station,
            fault_id=None,
            recorded_at=when,
            text=text,
        )
        history.link(fault_source, source, "inferred", "Same station and shift; no incident ID")
    quality = ("bad", "missing", "good")[number % 3]
    value = None if quality == "missing" else (-999.0 if quality == "bad" else rng.uniform(8, 12))
    source = history.source(
        "historian",
        key,
        start,
        station,
        {
            "incident": str(fault),
            "tag": "robot_current",
            "value": value,
            "unit": "A",
            "quality": quality,
        },
    )
    history.add(
        "historian_observation",
        key,
        source_record_id=source,
        station_id=station,
        fault_id=fault,
        observed_at=start,
        measurement_name="robot_current",
        value=value,
        unit="A",
        quality=quality,
    )
    history.link(fault_source, source, "direct", "Shared synthetic incident identifier")


def _station_history(
    history: EventHistory,
    rng: random.Random,
    shift: UUID,
    start: datetime,
    station: UUID,
    name: str,
    number: int,
) -> None:
    key = f"{shift}/{station}"
    fault_length = rng.randint(90, 240)
    if name == history.config.fault_focus:
        fault_length += 300  # Explicit fixture input; never a computed bottleneck conclusion.
    boundaries = [0, 60, 120, 120 + fault_length, 14400, 16200, 28800]
    states = ["starved", "blocked", "faulted", "running", "planned_downtime", "running"]
    fault_source = None
    fault_state = None
    for index, state in enumerate(states):
        begin = start + timedelta(seconds=boundaries[index])
        end = start + timedelta(seconds=boundaries[index + 1])
        state_key = f"{key}/{index}"
        source = history.source(
            "SCADA",
            state_key,
            begin,
            station,
            {"state": state, "start": begin.isoformat(), "end": end.isoformat()},
        )
        event = history.add(
            "station_event",
            state_key,
            source_record_id=source,
            station_id=station,
            shift_id=shift,
            start_time=begin,
            end_time=end,
            state=state,
        )
        if state == "faulted":
            fault_state = event
            fault_source = source
    begin = start + timedelta(seconds=120)
    end = begin + timedelta(seconds=fault_length)
    source = history.source(
        "SCADA",
        f"{key}/fault",
        begin,
        station,
        {"fault_code": "RBT-17", "start": begin.isoformat(), "end": end.isoformat()},
    )
    fault = history.add(
        "fault_event",
        key,
        source_record_id=source,
        station_id=station,
        station_event_id=fault_state,
        category="robot_fault",
        equipment_id=f"ROBOT-{name}",
        fault_code="RBT-17",
        start_time=begin,
        end_time=end,
    )
    history.link(source, fault_source, "direct", "Shared SCADA station-state interval")
    _supporting_records(history, rng, key, station, name, shift, begin, end, fault, source, number)


def _production_history(
    history: EventHistory,
    rng: random.Random,
    shift: UUID,
    start: datetime,
    stations: list[UUID],
    models: dict[str, UUID],
    release_sequence: int,
) -> int:
    for index in range(history.config.vehicles_per_shift):
        release_sequence += 1
        name = "SUV" if index % 2 == 0 else "Sedan"
        # Authored booking slots, with a 30-minute excluded break at hour 4.
        offset = 1000 + index * 24000 / history.config.vehicles_per_shift
        release = start + timedelta(seconds=offset + (1860 if offset >= 14340 else 0))
        vehicle = history.add(
            "vehicle",
            str(release_sequence),
            model_id=models[name],
            release_sequence=release_sequence,
            released_at=release,
        )
        for station_index, station in enumerate(stations):
            station_offset = offset + station_index * 60
            begin = start + timedelta(
                seconds=station_offset + (1860 if station_offset >= 14340 else 0)
            )
            end = begin + timedelta(seconds=rng.uniform(48, 55))
            key = f"{release_sequence}/{station_index + 1}"
            source = history.source(
                "MES",
                key,
                end,
                station,
                {
                    "vehicle_id": str(vehicle),
                    "model": name,
                    "shift_id": str(shift),
                    "start": begin.isoformat(),
                    "completion": end.isoformat(),
                },
            )
            history.add(
                "production_record",
                key,
                source_record_id=source,
                vehicle_id=vehicle,
                station_id=station,
                shift_id=shift,
                started_at=begin,
                completed_at=end,
            )
    return release_sequence


def _sops(history: EventHistory, stations: list[UUID]) -> None:
    for station, name in zip(stations, STATION_NAMES, strict=True):
        sections = [
            (
                "Record and escalate",
                f"At {name}, record the alarm ID and time, then notify maintenance. "
                "Preserve operator remarks and historian quality flags.",
            ),
            (
                "Human approval",
                "Only authorized plant personnel may approve equipment intervention. "
                "This synthetic example does not authorize production changes.",
            ),
        ]
        content = "\n\n".join(f"{title}\n{text}" for title, text in sections)
        source = history.source(
            "SOP",
            name,
            history.config.start_time,
            station,
            {"version": "1.0", "content": content},
            content,
        )
        document = history.add(
            "sop_document",
            name,
            source_record_id=source,
            station_id=station,
            title=f"{name} fault reporting",
            category="fault_reporting",
            version="1.0",
            effective_at=history.config.start_time,
            content=content,
        )
        for index, (title, text) in enumerate(sections, 1):
            section_source = history.source(
                "SOP",
                f"{name}/{index}",
                history.config.start_time,
                station,
                {"document_id": str(document), "version": "1.0", "section": index},
                text,
            )
            history.add(
                "sop_section",
                f"{name}/{index}",
                source_record_id=section_source,
                document_id=document,
                sequence=index,
                title=title,
                content=text,
            )
            history.link(source, section_source, "direct", "Versioned document section")


def generate_history(config: DatasetConfig) -> EventHistory:
    """Build one repeatable shared fixture, then project it to source-specific records."""
    history = EventHistory(config)
    rng = random.Random(config.seed)
    stations = [
        history.add("station", name, name=name, sequence=index, planned_cycle_seconds=60.0)
        for index, name in enumerate(STATION_NAMES, 1)
    ]
    for index in range(6):
        history.add(
            "buffer",
            str(index),
            upstream_station_id=stations[index],
            downstream_station_id=stations[index + 1],
            capacity=5,
        )
    models = {name: history.add("vehicle_model", name, name=name) for name in ("SUV", "Sedan")}
    release_sequence = 0
    for day in range(config.days):
        for shift_index in range(2):
            start = config.start_time + timedelta(days=day, hours=shift_index * 8)
            shift = history.add(
                "shift",
                f"{day}/{shift_index}",
                name=f"shift_{shift_index + 1}",
                start_time=start,
                end_time=start + timedelta(hours=8),
                timezone_name="UTC",
            )
            history.add(
                "calendar_exclusion",
                str(shift),
                shift_id=shift,
                start_time=start + timedelta(hours=4),
                end_time=start + timedelta(hours=4, minutes=30),
                reason="planned_break",
            )
            for index, (station, name) in enumerate(zip(stations, STATION_NAMES, strict=True)):
                number = (day * 2 + shift_index) * 7 + index
                _station_history(history, rng, shift, start, station, name, number)
            source = history.source(
                "shift_notes",
                f"irrelevant/{shift}",
                start,
                None,
                {"note": "Canteen menu changed; no production incident recorded."},
                "Canteen menu changed; no production incident recorded.",
            )
            history.add(
                "shift_handover_note",
                f"irrelevant/{shift}",
                source_record_id=source,
                shift_id=shift,
                station_id=None,
                fault_id=None,
                recorded_at=start,
                text="Canteen menu changed; no production incident recorded.",
            )
            opened = start + timedelta(hours=3)
            description = "Preventive tooling inspection; no fault identifier recorded."
            source = history.source(
                "CMMS",
                f"unlinked/{shift}",
                opened,
                stations[0],
                {"description": description},
                description,
            )
            history.add(
                "maintenance_work_order",
                f"unlinked/{shift}",
                source_record_id=source,
                station_id=stations[0],
                fault_id=None,
                opened_at=opened,
                closed_at=opened + timedelta(minutes=20),
                description=description,
                status="closed",
                recorded_cause=None,
            )
            release_sequence = _production_history(
                history,
                rng,
                shift,
                start,
                stations,
                models,
                release_sequence,
            )
    _sops(history, stations)
    return history
