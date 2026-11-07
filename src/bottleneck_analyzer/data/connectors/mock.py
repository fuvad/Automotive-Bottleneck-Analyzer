"""Read-only logical source connectors over retained synthetic source records."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Connection

from bottleneck_analyzer.db.models.production import SourceRecord

SOURCE_SYSTEMS = ("MES", "SCADA", "historian", "CMMS", "Andon", "shift_notes", "SOP")


def read_source_records(
    connection: Connection, dataset_id: UUID, system: str
) -> Iterator[dict[str, Any]]:
    """Expose original and normalized metadata without unrestricted agent SQL."""
    if system not in SOURCE_SYSTEMS:
        raise ValueError(f"Unsupported source system: {system}")
    query = select(
        SourceRecord.id,
        SourceRecord.source_id,
        SourceRecord.recorded_at,
        SourceRecord.station_id,
        SourceRecord.raw,
        SourceRecord.text_content,
        SourceRecord.original_path,
    ).where(SourceRecord.dataset_id == dataset_id, SourceRecord.system == system)
    for row in connection.execute(query).mappings():
        yield dict(row)


def read_source_file(path: Path) -> Iterator[dict[str, Any]]:
    """Read local export rows; source fields stay intact inside the raw payload."""
    with path.open(encoding="utf-8", newline="") as handle:
        if path.suffix == ".csv":
            for row in csv.DictReader(handle):
                row["raw"] = json.loads(row["raw"])
                yield row
        elif path.suffix == ".jsonl":
            for line in handle:
                yield json.loads(line)
        else:
            raise ValueError("Source exports must be CSV or JSONL")
