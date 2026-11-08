"""Simulation persistence tests reuse Stage 2's rollback-only isolated schema."""

import pytest
from sqlalchemy import select

from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.data.validation import DatasetValidationError
from bottleneck_analyzer.db.models.production import Dataset, SimulationRun
from bottleneck_analyzer.domain.manufacturing import DatasetConfig
from bottleneck_analyzer.simulation.config import SimulationConfig, updated
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.persistence import persist_result, topology_from_dataset

from .test_business_schema import schema_connection as schema_connection


def test_simulated_history_persists_idempotently_and_preserves_authored_fixture(schema_connection):
    reference = generate_history(
        DatasetConfig(name="authored-reference", days=1, vehicles_per_shift=8)
    )
    load_history(schema_connection, reference)
    before = schema_connection.scalar(
        select(Dataset.content_hash).where(Dataset.id == reference.dataset_id)
    )
    config = SimulationConfig(
        name="sim-integration", days=1, sop_reference_dataset="authored-reference"
    )
    config = topology_from_dataset(schema_connection, config)
    assert config.buffer_capacities == (5, 5, 5, 5, 5, 5)
    result = run_simulation(config)
    assert persist_result(schema_connection, result)["created"]
    assert not persist_result(schema_connection, result)["created"]
    assert (
        schema_connection.scalar(
            select(Dataset.content_hash).where(Dataset.id == reference.dataset_id)
        )
        == before
    )
    assert (
        schema_connection.scalar(select(Dataset.provenance).where(Dataset.name == config.name))
        == "simulation"
    )
    stored = schema_connection.execute(select(SimulationRun.__table__)).mappings().first()
    assert stored["seed"] == config.seed
    assert stored["results"]["metrics"]["completed"] == result.metrics["completed"]
    assert load_history(schema_connection, reference)["created"] is False
    changed = run_simulation(updated(config, seed=99))
    with pytest.raises(DatasetValidationError, match="different content"):
        persist_result(schema_connection, changed)


def test_invalid_output_cannot_be_persisted(schema_connection):
    reference = generate_history(
        DatasetConfig(name="authored-reference", days=1, vehicles_per_shift=8)
    )
    load_history(schema_connection, reference)
    result = run_simulation(
        SimulationConfig(name="invalid-sim", days=1, sop_reference_dataset="authored-reference")
    )
    result.metrics["completed"] += 1
    with pytest.raises(ValueError):
        persist_result(schema_connection, result)
    assert schema_connection.scalar(select(Dataset.id).where(Dataset.name == "invalid-sim")) is None
