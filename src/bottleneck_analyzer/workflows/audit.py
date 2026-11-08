"""Durable investigation state in the existing table; never edit source history."""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import insert, select, text, update
from sqlalchemy.engine import Connection, Engine

from bottleneck_analyzer.agents.contracts import DatasetContext, WorkflowState
from bottleneck_analyzer.analytics.calendar import build_segments
from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.analytics.repository import AnalyticsRepository
from bottleneck_analyzer.db.models.production import InvestigationAudit, ModelConfiguration
from bottleneck_analyzer.simulation.config import SimulationConfig


class AuditUnavailable(RuntimeError):
    pass


class AuditWriter(Protocol):
    def create(self, state: WorkflowState) -> None: ...
    def save(self, state: WorkflowState) -> None: ...


def dataset_context(connection: Connection, scope: AnalyticsScope) -> DatasetContext:
    repo = AnalyticsRepository(connection, scope.dataset)
    build_segments(repo.dataset, repo.shifts, repo.exclusions, scope)
    configs = (
        connection.execute(
            select(ModelConfiguration.__table__).where(
                ModelConfiguration.dataset_id == repo.dataset_id
            )
        )
        .mappings()
        .all()
    )
    config = configs[0] if len(configs) == 1 else None
    return DatasetContext(
        dataset_id=repo.dataset_id,
        name=repo.dataset["name"],
        provenance=repo.dataset["provenance"],
        content_hash=repo.dataset["content_hash"],
        start_time=repo.dataset["start_time"],
        end_time=repo.dataset["end_time"],
        configuration_id=config["id"] if config else None,
        configuration_approved=bool(config and config["approved_by"] and config["approved_at"]),
        simulation_config=SimulationConfig.model_validate(config["parameters"]) if config else None,
    )


def load_context(engine: Engine, scope: AnalyticsScope) -> DatasetContext:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            return dataset_context(connection, scope)


class PostgresAudit:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, state: WorkflowState) -> None:
        with self.engine.begin() as connection:
            create_audit(connection, state)

    def save(self, state: WorkflowState) -> None:
        with self.engine.begin() as connection:
            save_audit(connection, state)


def create_audit(connection: Connection, state: WorkflowState) -> None:
    connection.execute(
        insert(InvestigationAudit).values(
            id=state.investigation_id,
            dataset_id=state.context.dataset_id,
            question=state.question,
            route="pending",
            state=state.model_dump(mode="json"),
            recorded_at=datetime.now(UTC),
            final_answer=None,
        )
    )


def save_audit(connection: Connection, state: WorkflowState) -> None:
    result = connection.execute(
        update(InvestigationAudit)
        .where(
            InvestigationAudit.id == state.investigation_id,
            InvestigationAudit.dataset_id == state.context.dataset_id,
        )
        .values(
            route=state.plan.intent.value if state.plan else state.outcome or "pending",
            state=state.model_dump(mode="json"),
            final_answer=state.response.answer if state.response else None,
        )
    )
    if result.rowcount != 1:
        raise AuditUnavailable("Investigation audit record is missing")
