"""One process-local execution slot; PostgreSQL remains the durable audit."""

from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, Lock
from time import monotonic
from typing import Protocol
from uuid import UUID

from sqlalchemy.engine import Engine

from bottleneck_analyzer.agents.contracts import (
    InvestigationRequest,
    InvestigationResponse,
    WorkflowState,
)
from bottleneck_analyzer.api.settings import APISettings
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.workflows.audit import AuditWriter, PostgresAudit
from bottleneck_analyzer.workflows.graph import InvestigationWorkflow


class AdmissionStopped(RuntimeError):
    """Raised by the adapter before any graph execution is allowed."""


class WorkflowRunner(Protocol):
    def run(self, request: InvestigationRequest) -> InvestigationResponse: ...


class AdmissionError(RuntimeError):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status


@dataclass
class Submission:
    key: UUID
    fingerprint: str
    deadline: float
    lock: Lock = field(default_factory=Lock)
    gate: Event = field(default_factory=Event)
    committed_id: UUID | None = None
    candidate_id: UUID | None = None
    accepted: bool = False
    abandoned: bool = False
    worker_active: bool = True
    error: str | None = None
    error_status: int = 503

    def accept(self) -> bool:
        with self.lock:
            if self.accepted:
                return True
            if self.abandoned or monotonic() >= self.deadline:
                self.abandoned = True
                self.gate.set()
                return False
            if self.committed_id is None:
                return False
            self.accepted = True
            self.gate.set()
            return True

    def abandon(self) -> None:
        with self.lock:
            if not self.accepted:
                self.abandoned = True
                self.gate.set()

    def view(self) -> dict:
        with self.lock:
            if self.accepted:
                admission = "accepted"
            elif self.worker_active:
                admission = "pending_reconciliation" if self.abandoned else "pending"
            elif self.committed_id:
                admission = "rejected_execution_not_started"
            elif self.error == "commit_unconfirmed":
                admission = "unconfirmed"
            else:
                admission = "rejected"
            return {
                "submission_key": str(self.key),
                "admission": admission,
                "investigation_id": str(self.committed_id) if self.committed_id else None,
                "worker_active": self.worker_active,
                "error": self.error,
                "process_local": True,
            }


class AdmissionAudit:
    """Wait only AFTER the delegate's create transaction has committed."""

    def __init__(self, delegate: AuditWriter, submission: Submission):
        self.delegate, self.submission = delegate, submission

    def create(self, state: WorkflowState) -> None:
        item = self.submission
        with item.lock:
            item.candidate_id = state.investigation_id
            if item.abandoned or monotonic() >= item.deadline:
                raise AdmissionStopped()
        try:
            self.delegate.create(state)
        except Exception:
            with item.lock:
                item.error = "commit_unconfirmed"
            raise
        # PostgresAudit.create has returned: no transaction is held at this gate.
        with item.lock:
            item.committed_id = state.investigation_id
        item.gate.wait(max(0, item.deadline - monotonic()))
        with item.lock:
            if not item.accepted:
                item.abandoned = True
                item.gate.set()
                raise AdmissionStopped()

    def save(self, state: WorkflowState) -> None:
        self.delegate.save(state)


class InvestigationRuntime:
    def __init__(
        self,
        settings: APISettings | None = None,
        *,
        engine_factory: Callable[[], Engine] = create_db_engine,
        workflow_factory: Callable[..., WorkflowRunner] = InvestigationWorkflow,
        audit_factory: Callable[[Engine], AuditWriter] = PostgresAudit,
    ):
        self.settings = settings or APISettings()
        self.engine_factory = engine_factory
        self.workflow_factory, self.audit_factory = workflow_factory, audit_factory
        self._engine: Engine | None = None
        self._engine_lock = Lock()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="investigation")
        self._items: OrderedDict[UUID, Submission] = OrderedDict()
        self._active = False
        self._closing = False

    @property
    def engine(self) -> Engine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = self.engine_factory()
            return self._engine

    def submit(self, key: UUID, request: InvestigationRequest) -> Submission:
        fingerprint = request.model_dump_json()
        with self._lock:
            if key in self._items:
                item = self._items[key]
                if item.fingerprint != fingerprint:
                    raise AdmissionError("submission_conflict", 409)
                return item
            if self._closing:
                raise AdmissionError("shutting_down", 503)
            if self._active:
                raise AdmissionError("busy", 429)
            while len(self._items) >= self.settings.submission_history_limit:
                self._items.popitem(last=False)
            item = Submission(
                key, fingerprint, monotonic() + self.settings.admission_timeout_seconds
            )
            self._items[key] = item
            self._active = True
            self._executor.submit(self._run, item, request)
            return item

    def _run(self, item: Submission, request: InvestigationRequest) -> None:
        scope_validation = False
        try:
            audit = AdmissionAudit(self.audit_factory(self.engine), item)
            workflow = self.workflow_factory(self.engine, audit=audit)
            scope_validation = True
            workflow.run(request)
        except Exception as exc:
            with item.lock:
                if item.error is None:
                    item.error = "execution_unconfirmed" if item.accepted else "admission_failed"
                    if (
                        scope_validation
                        and isinstance(exc, ValueError)
                        and item.candidate_id is None
                    ):
                        item.error, item.error_status = "invalid_scope", 422
        finally:
            with item.lock:
                item.worker_active = False
            with self._lock:
                self._active = False

    def get(self, key: UUID) -> Submission | None:
        with self._lock:
            return self._items.get(key)

    def execution(self, investigation_id: UUID) -> str:
        with self._lock:
            items = list(self._items.values())
        for item in items:
            with item.lock:
                if item.committed_id == investigation_id:
                    if item.accepted and item.worker_active:
                        return "active"
                    if not item.accepted:
                        return "not_started"
        return "unconfirmed"

    def close(self) -> None:
        with self._lock:
            self._closing = True
            items = list(self._items.values())
        for item in items:
            item.abandon()  # Accepted work is deliberately NOT cancelled.
        self._executor.shutdown(wait=True, cancel_futures=False)
        if self._engine is not None:
            self._engine.dispose()
