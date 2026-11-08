"""Read-only, five-exchange audit context. No chat store, queue, or trusted memory."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine

from bottleneck_analyzer.agents.contracts import ConversationTurn, DatasetContext
from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.db.models.production import InvestigationAudit

MAX_CONTEXT_EXCHANGES = 5


def context_row(connection: Connection, identifier: UUID) -> dict | None:
    state = InvestigationAudit.state
    row = (
        connection.execute(
            select(
                InvestigationAudit.id,
                InvestigationAudit.dataset_id,
                state["request"]["previous_investigation_id"].label("previous_id"),
                state["context"]["content_hash"].label("content_hash"),
                state["response"]["investigation_id"].label("response_id"),
                state["response"]["audit_id"].label("audit_id"),
                state["response"]["question"].label("question"),
                state["response"]["answer"].label("answer"),
                state["response"]["scope"].label("scope"),
                state["response"]["outcome"].label("outcome"),
                state["response"]["clarification"].label("clarification"),
                state["response"]["historical"]["leading_candidate"].label("leading_candidate"),
                state["response"]["historical"]["historical_jph"].label("historical_jph"),
                state["plan"]["scenario"]["request"].label("scenario"),
                state["response"]["warnings"].label("warnings"),
                state["response"]["evidence"]["interpretations"].label("interpretations"),
            ).where(InvestigationAudit.id == identifier)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def resolve_context(
    previous_id: UUID | None,
    scope: AnalyticsScope,
    dataset: DatasetContext,
    fetch: Callable[[UUID], dict | None],
) -> tuple[list[ConversationTurn], list[str]]:
    turns, notices, seen = [], [], set()
    while previous_id is not None and len(turns) < MAX_CONTEXT_EXCHANGES:
        if previous_id in seen:
            raise ValueError("Conversation references contain a cycle")
        seen.add(previous_id)
        row = fetch(previous_id)
        if (
            not row
            or str(row.get("audit_id")) != str(row["id"])
            or str(row.get("response_id")) != str(row["id"])
        ):
            raise ValueError("Previous investigation has no confirmed final response")
        if (
            str(row["dataset_id"]) != str(dataset.dataset_id)
            or row["content_hash"] != dataset.content_hash
        ):
            raise ValueError("Previous investigation belongs to another dataset or version")
        previous_scope = AnalyticsScope.model_validate(row["scope"])
        if (
            previous_scope.start_time != scope.start_time
            or previous_scope.end_time != scope.end_time
        ):
            notices.append("Prior context omitted because the selected analysis period changed.")
            break
        outcome = row["outcome"]
        usable = outcome in ("completed", "incomplete")
        turns.append(
            ConversationTurn(
                investigation_id=row["id"],
                question=row["question"][:2000],
                answer=(row.get("answer") or "").split("\n\n")[0][:1600] if usable else "",
                scope=previous_scope,
                outcome=outcome,
                clarification=(row.get("clarification") or "")[:1000] or None,
                leading_candidate=row.get("leading_candidate") if usable else None,
                historical_jph=row.get("historical_jph") if usable else None,
                scenario=row.get("scenario") if usable else None,
                evidence_labels=list(
                    dict.fromkeys(item["label"] for item in row.get("interpretations") or [])
                )[:4]
                if usable
                else [],
                warnings=[str(w)[:300] for w in (row.get("warnings") or [])[:3]],
            )
        )
        previous_id = UUID(str(row["previous_id"])) if row.get("previous_id") else None
    return list(reversed(turns)), notices


def load_conversation(
    engine: Engine,
    previous_id: UUID,
    scope: AnalyticsScope,
    dataset: DatasetContext,
) -> tuple[list[ConversationTurn], list[str]]:
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '10000ms'"))
        return resolve_context(previous_id, scope, dataset, lambda i: context_row(connection, i))
