"""Bounded SELECT-only projections; no second audit writer or source mutations."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Text, case, cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from bottleneck_analyzer.db.models.production import (
    Dataset,
    InvestigationAudit,
    Shift,
    Station,
    VehicleModel,
)


class APIRepository:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def read(self):
        with self.engine.connect() as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '10000ms'"))
            yield connection

    def datasets(self, limit: int, offset: int) -> list[dict]:
        with self.read() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(
                        Dataset.id,
                        Dataset.name,
                        Dataset.provenance,
                        Dataset.start_time,
                        Dataset.end_time,
                    )
                    .order_by(Dataset.name)
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            ]

    def options(self, dataset_id: UUID) -> dict | None:
        with self.read() as c:
            exists = c.scalar(select(Dataset.id).where(Dataset.id == dataset_id))
            if exists is None:
                return None
            return {
                "stations": list(
                    c.scalars(
                        select(Station.name)
                        .where(Station.dataset_id == dataset_id)
                        .order_by(Station.sequence)
                        .limit(7)
                    )
                ),
                "models": list(
                    c.scalars(
                        select(VehicleModel.name)
                        .where(VehicleModel.dataset_id == dataset_id)
                        .order_by(VehicleModel.name)
                        .limit(2)
                    )
                ),
                "shifts": [
                    dict(r)
                    for r in c.execute(
                        select(Shift.id, Shift.name, Shift.start_time, Shift.end_time)
                        .where(Shift.dataset_id == dataset_id)
                        .order_by(Shift.start_time)
                        .limit(1000)
                    ).mappings()
                ],
            }

    def history(self, limit: int, offset: int) -> list[dict]:
        with self.read() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(
                        InvestigationAudit.id,
                        InvestigationAudit.dataset_id,
                        InvestigationAudit.question,
                        InvestigationAudit.recorded_at,
                    )
                    .order_by(InvestigationAudit.recorded_at.desc(), InvestigationAudit.id)
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            ]

    def audit(self, investigation_id: UUID, *, result: bool = False) -> dict | None:
        state = InvestigationAudit.state
        columns = [
            InvestigationAudit.id,
            InvestigationAudit.dataset_id,
            InvestigationAudit.recorded_at,
            state["events"].label("events"),
            state["status"].label("status"),
            state["response"]["audit_id"].label("audit_id"),
            state["response"]["investigation_id"].label("response_id"),
            state["response"]["outcome"].label("outcome"),
        ]
        if result:
            response = case(
                (func.jsonb_typeof(state["response"]) == "object", state["response"]),
                else_=literal({}, JSONB),
            )
            # Large per-replication payload/configuration stays in the original audit.
            for path in (
                "{simulation,comparison,runs}",
                "{simulation,comparison,baseline_config}",
                "{simulation,comparison,scenario_config}",
            ):
                response = response.op("#-")(cast(path.strip("{}").split(","), ARRAY(Text)))
            columns += [
                response.label("response"),
                state["plan"]["scenario"].label("scenario_request"),
                state["analytics"]["overall"]["line"].label("historical_line"),
                state["analytics"]["overall"]["stations"].label("historical_stations"),
                state["analytics"]["assumptions"].label("historical_assumptions"),
                state["analytics"]["provenance"].label("historical_origin"),
            ]
        with self.read() as c:
            row = (
                c.execute(select(*columns).where(InvestigationAudit.id == investigation_id))
                .mappings()
                .first()
            )
            return dict(row) if row else None
