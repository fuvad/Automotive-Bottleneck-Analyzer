"""Atomic, append-only dataset loading using existing SQLAlchemy infrastructure."""

from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Connection

from bottleneck_analyzer.data.generators.history import EventHistory
from bottleneck_analyzer.data.validation import DatasetValidationError, validate_history
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.models.production import Dataset


def load_history(connection: Connection, history: EventHistory) -> dict[str, Any]:
    """Validate and insert within the caller's transaction, or verify an exact replay.

    The caller must use engine.begin(). No records are deleted or overwritten.
    An advisory lock serializes concurrent attempts for the same dataset identity.
    """
    report = validate_history(history)
    fingerprint = history.fingerprint()
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
        {"name": str(history.dataset_id)},
    )
    existing = (
        connection.execute(select(Dataset.__table__).where(Dataset.id == history.dataset_id))
        .mappings()
        .first()
    )
    if existing is not None:
        if existing["content_hash"] != fingerprint:
            raise DatasetValidationError("Dataset identity already exists with different content")
        counts = persisted_counts(connection, history)
        if counts != history.counts():
            raise DatasetValidationError(
                "Existing dataset is incomplete; refusing to silently repair it"
            )
        verify_persisted_content(connection, history)
        return {**report, "created": False, "fingerprint": fingerprint}
    connection.execute(
        insert(Dataset),
        {
            "id": history.dataset_id,
            "name": history.config.name,
            "seed": history.config.seed,
            "start_time": history.config.start_time,
            "end_time": history.config.end_time,
            "config": history.config.model_dump(mode="json"),
            "content_hash": fingerprint,
            "provenance": "authored_fixture",
        },
    )
    for table in Base.metadata.sorted_tables:
        rows = history.rows.get(table.name, [])
        for offset in range(0, len(rows), 2000):
            connection.execute(insert(table), rows[offset : offset + 2000])
    if persisted_counts(connection, history) != history.counts():
        raise DatasetValidationError("Persisted counts do not match the validated dataset")
    verify_persisted_content(connection, history)
    return {**report, "created": True, "fingerprint": fingerprint}


def persisted_counts(connection: Connection, history: EventHistory) -> dict[str, int]:
    return {
        name: connection.execute(
            select(func.count())
            .select_from(Base.metadata.tables[name])
            .where(Base.metadata.tables[name].c.dataset_id == history.dataset_id)
        ).scalar_one()
        for name in sorted(history.rows)
    }


def verify_persisted_content(connection: Connection, history: EventHistory) -> None:
    """Check retained values as well as counts, including on an idempotent replay."""
    for name, rows in history.rows.items():
        table = Base.metadata.tables[name]
        expected = {row["id"]: row for row in rows}
        statement = (
            select(table)
            .where(table.c.dataset_id == history.dataset_id)
            .execution_options(stream_results=True)
        )
        for stored in connection.execute(statement).mappings():
            original = expected.get(stored["id"])
            if original is None or any(stored[key] != value for key, value in original.items()):
                raise DatasetValidationError(f"Persisted content differs from fixture: {name}")
