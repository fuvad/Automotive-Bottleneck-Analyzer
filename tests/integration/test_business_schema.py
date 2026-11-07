"""Opt-in live tests restricted to a new schema in a rollback-only transaction.

Run with STAGE2_TEST_POSTGRES=1. Every write uses a unique stage2_test_<uuid>
schema and a caller-owned transaction; no public tables or data are modified.
The existing database role has no CREATEDB privilege, so this is the isolated
schema alternative to creating a separate test database.
"""

import os
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from bottleneck_analyzer.data.connectors.mock import read_source_records
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history, persisted_counts
from bottleneck_analyzer.data.validation import DatasetValidationError
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.models.production import (
    Dataset,
    FaultEvent,
    MaintenanceWorkOrder,
    ProductionRecord,
    SOPDocument,
    SourceRecord,
    Station,
)
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.domain.manufacturing import DatasetConfig


@pytest.fixture
def schema_connection():
    if os.getenv("STAGE2_TEST_POSTGRES") != "1":
        pytest.skip("Set STAGE2_TEST_POSTGRES=1 to run rollback-only isolated-schema tests")
    engine = create_db_engine()
    schema = f"stage2_test_{uuid4().hex}"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            assert connection.scalar(text("SELECT current_schema()")) == schema
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            cfg.attributes["version_table_schema"] = schema
            command.upgrade(cfg, "head")
            assert set(Base.metadata.tables) <= set(
                inspect(connection).get_table_names(schema=schema)
            )
            yield connection
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        assert not inspect(connection).has_schema(schema)
    engine.dispose()


def small_history(**overrides):
    return generate_history(
        DatasetConfig(
            **{
                "name": "integration-fixture",
                "days": 1,
                "vehicles_per_shift": 6,
                **overrides,
            }
        )
    )


def test_migration_and_metadata_are_consistent(schema_connection) -> None:
    connection = schema_connection
    assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())
    schema = connection.scalar(text("SELECT current_schema()"))
    assert connection.scalar(text(f'SELECT version_num FROM "{schema}".alembic_version')) == "0001"
    context = MigrationContext.configure(
        connection,
        opts={
            "version_table_schema": schema,
            "include_object": lambda obj, name, kind, reflected, compare_to: (
                name != "alembic_version"
            ),
        },
    )
    assert compare_metadata(context, Base.metadata) == []


def test_atomic_load_replay_fresh_identity_and_orm_relationships(schema_connection) -> None:
    history = small_history()
    first = load_history(schema_connection, history)
    second = load_history(schema_connection, history)
    assert first["created"] is True
    assert second["created"] is False
    assert persisted_counts(schema_connection, history) == history.counts()
    with Session(bind=schema_connection, join_transaction_mode="create_savepoint") as session:
        dataset = session.get(Dataset, history.dataset_id)
        assert len(dataset.stations) == 7
        production = session.scalars(select(ProductionRecord)).first()
        assert production.vehicle.model.name in {"SUV", "Sedan"}
        maintenance = session.scalars(select(MaintenanceWorkOrder)).first()
        assert maintenance.fault.station.name
        document = session.scalars(select(SOPDocument)).first()
        assert document.version == "1.0"
        assert len(document.sections) == 2
    fresh = small_history(name="another-fixture")
    assert load_history(schema_connection, fresh)["created"]
    assert persisted_counts(schema_connection, history) == history.counts()
    with pytest.raises(DatasetValidationError, match="different content"):
        load_history(schema_connection, small_history(seed=99))


@pytest.mark.parametrize(
    "mutation", ["missing_name", "duplicate_sequence", "foreign_key", "category"]
)
def test_database_enforces_required_fields_and_constraints(schema_connection, mutation) -> None:
    history = small_history()
    load_history(schema_connection, history)
    if mutation in {"missing_name", "duplicate_sequence"}:
        row = history.rows["station"][0].copy()
        row["id"] = uuid4()
        if mutation == "missing_name":
            row["name"] = None
        table = Station.__table__
    else:
        row = history.rows["fault_event"][0].copy()
        row["id"] = uuid4()
        if mutation == "foreign_key":
            row["station_id"] = uuid4()
        else:
            row["category"] = "invented"
        table = FaultEvent.__table__
    with pytest.raises(IntegrityError), schema_connection.begin_nested():
        # UPDATE the fixture row for FK/category cases so unique keys do not mask those checks.
        if table.name == "fault_event":
            key = "station_id" if mutation == "foreign_key" else "category"
            schema_connection.execute(
                table.update()
                .where(table.c.id == history.rows["fault_event"][0]["id"])
                .values({key: row[key]})
            )
        else:
            schema_connection.execute(insert(table), row)


def test_computed_durations_search_vector_and_source_connector(schema_connection) -> None:
    history = small_history()
    load_history(schema_connection, history)
    row = schema_connection.execute(select(FaultEvent.__table__)).mappings().first()
    assert row["duration_seconds"] == (row["end_time"] - row["start_time"]).total_seconds()
    assert row["duration_seconds"] > 0
    assert schema_connection.scalar(select(SourceRecord.search_vector).limit(1)) is not None
    records = list(read_source_records(schema_connection, history.dataset_id, "SOP"))
    assert len(records) == 21
    assert all(record["source_id"] and record["raw"] for record in records)
    assert schema_connection.scalar(select(SourceRecord.embedding).limit(1)) is None
    with pytest.raises(ValueError):
        list(read_source_records(schema_connection, history.dataset_id, "unapproved"))


def test_database_rejects_reversed_event_interval(schema_connection) -> None:
    history = small_history()
    load_history(schema_connection, history)
    fault = history.rows["fault_event"][0]
    with pytest.raises(IntegrityError), schema_connection.begin_nested():
        schema_connection.execute(
            FaultEvent.__table__.update()
            .where(FaultEvent.id == fault["id"])
            .values(end_time=fault["start_time"])
        )


def test_replay_rejects_stored_content_drift(schema_connection) -> None:
    history = small_history()
    load_history(schema_connection, history)
    schema_connection.execute(
        Station.__table__.update()
        .where(Station.id == history.rows["station"][0]["id"])
        .values(planned_cycle_seconds=61)
    )
    with pytest.raises(DatasetValidationError, match="Persisted content differs"):
        load_history(schema_connection, history)


def test_failed_load_rolls_back_all_insertions(schema_connection) -> None:
    history = small_history()
    # Force a server-side failure after the dataset row would have been inserted.
    history.rows["station"][0]["planned_cycle_seconds"] = -1
    with pytest.raises(IntegrityError), schema_connection.begin_nested():
        load_history(schema_connection, history)
    assert (
        schema_connection.scalar(select(Dataset.id).where(Dataset.id == history.dataset_id)) is None
    )
