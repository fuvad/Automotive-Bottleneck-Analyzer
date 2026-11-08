"""Deterministic admission races; no provider calls or development writes."""

import asyncio
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from bottleneck_analyzer.agents.contracts import InvestigationRequest
from bottleneck_analyzer.api.routes import investigate
from bottleneck_analyzer.api.runtime import (
    AdmissionAudit,
    AdmissionError,
    AdmissionStopped,
    InvestigationRuntime,
    Submission,
)
from bottleneck_analyzer.api.settings import APISettings


def payload():
    return InvestigationRequest(question="Analyze the line", scope={"dataset": "fixture"})


def wait_until(predicate):
    deadline = monotonic() + 3
    while not predicate():
        assert monotonic() < deadline, "Synchronization condition timed out"
        Event().wait(0.002)


class ControlledAudit:
    def __init__(self):
        self.entered, self.commit, self.exited = Event(), Event(), Event()
        self.fail = False

    def create(self, state):
        self.entered.set()
        assert self.commit.wait(3)
        self.exited.set()
        if self.fail:
            raise RuntimeError("secret connection string")

    def save(self, state):
        pass


def test_no_acceptance_or_graph_before_commit_and_no_transaction_at_gate():
    item = Submission(uuid4(), "request", monotonic() + 3)
    delegate = ControlledAudit()
    state = SimpleNamespace(investigation_id=uuid4())
    ran = Event()

    def worker():
        AdmissionAudit(delegate, item).create(state)
        ran.set()

    thread = Thread(target=worker)
    thread.start()
    assert delegate.entered.wait(2)
    assert not item.accept() and not ran.is_set()
    delegate.commit.set()
    wait_until(lambda: item.committed_id is not None)
    assert delegate.exited.is_set()  # create/transaction finished before gate.
    assert not ran.is_set()
    assert item.accept()
    thread.join(2)
    assert ran.is_set() and not thread.is_alive()


@pytest.mark.parametrize("stop", ["timeout", "disconnect"])
def test_late_commit_after_abandonment_never_opens_graph(stop):
    delegate = ControlledAudit()
    item = Submission(uuid4(), "request", monotonic() + 3)
    state = SimpleNamespace(investigation_id=uuid4())
    stopped = Event()

    def worker():
        with pytest.raises(AdmissionStopped):
            AdmissionAudit(delegate, item).create(state)
        stopped.set()

    thread = Thread(target=worker)
    thread.start()
    assert delegate.entered.wait(2)
    if stop == "timeout":
        with item.lock:
            item.deadline = monotonic() - 1
    item.abandon()
    delegate.commit.set()
    thread.join(2)
    assert stopped.is_set() and not item.accept()
    item.worker_active = False
    assert item.view()["admission"] == "rejected_execution_not_started"


def test_acceptance_winning_disconnect_race_continues():
    item = Submission(uuid4(), "request", monotonic() + 3, committed_id=uuid4())
    assert item.accept()
    item.abandon()
    assert item.accepted and not item.abandoned
    assert item.view()["admission"] == "accepted"


def test_uncertain_commit_has_no_confirmed_id_or_execution():
    delegate = ControlledAudit()
    delegate.fail = True
    delegate.commit.set()
    item = Submission(uuid4(), "request", monotonic() + 3)
    with pytest.raises(RuntimeError):
        AdmissionAudit(delegate, item).create(SimpleNamespace(investigation_id=uuid4()))
    item.worker_active = False
    assert item.candidate_id and item.committed_id is None
    assert item.view()["admission"] == "unconfirmed"
    assert "secret" not in str(item.view())


def controlled_runtime(timeout=2):
    delegate = ControlledAudit()
    ran, finish = Event(), Event()

    class Workflow:
        def __init__(self, engine, audit):
            self.audit = audit

        def run(self, request):
            self.audit.create(SimpleNamespace(investigation_id=uuid4()))
            ran.set()
            assert finish.wait(3)

    runtime = InvestigationRuntime(
        APISettings(_env_file=None, admission_timeout_seconds=timeout),
        engine_factory=Mock,
        audit_factory=lambda engine: delegate,
        workflow_factory=Workflow,
    )
    return runtime, delegate, ran, finish


def test_timeout_keeps_slot_until_worker_exits_and_deduplicates():
    runtime, delegate, ran, finish = controlled_runtime()
    try:
        key = uuid4()
        item = runtime.submit(key, payload())
        assert delegate.entered.wait(2)
        item.abandon()
        assert runtime.submit(key, payload()) is item
        with pytest.raises(AdmissionError) as busy:
            runtime.submit(uuid4(), payload())
        assert busy.value.status == 429
        changed = payload().model_copy(update={"question": "A different question"})
        with pytest.raises(AdmissionError) as conflict:
            runtime.submit(key, changed)
        assert conflict.value.status == 409
        delegate.commit.set()
        wait_until(lambda: not item.worker_active)
        assert not ran.is_set()
        assert runtime.get(key) is item
    finally:
        delegate.commit.set()
        finish.set()
        runtime.close()


@pytest.mark.parametrize("disconnect", [True, False])
def test_http_disconnect_and_timeout_during_commit_keep_worker_registered(disconnect):
    runtime, delegate, ran, finish = controlled_runtime(timeout=0.04)
    key = uuid4()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(investigations=runtime)))

    async def disconnected():
        assert delegate.entered.wait(2)
        return disconnect

    request.is_disconnected = disconnected
    try:
        with pytest.raises(HTTPException) as error:
            asyncio.run(investigate(payload(), request, key))
        assert error.value.status_code == 503
        item = runtime.get(key)
        assert item.worker_active
        with pytest.raises(AdmissionError):
            runtime.submit(uuid4(), payload())
        delegate.commit.set()
        wait_until(lambda: not item.worker_active)
        assert not ran.is_set()
    finally:
        delegate.commit.set()
        finish.set()
        runtime.close()


def test_shutdown_waits_for_accepted_work_and_rejects_new_work():
    runtime, delegate, ran, finish = controlled_runtime()
    item = runtime.submit(uuid4(), payload())
    assert delegate.entered.wait(2)
    delegate.commit.set()
    wait_until(lambda: item.committed_id is not None)
    assert item.accept() and ran.wait(2)
    closed = Event()
    thread = Thread(target=lambda: (runtime.close(), closed.set()))
    thread.start()
    wait_until(lambda: runtime._closing)
    assert not closed.is_set()
    with pytest.raises(AdmissionError) as error:
        runtime.submit(uuid4(), payload())
    assert error.value.code == "shutting_down"
    finish.set()
    thread.join(2)
    assert closed.is_set()
    runtime.engine.dispose.assert_called_once()


def test_final_audit_failure_does_not_claim_finalization():
    runtime, delegate, ran, finish = controlled_runtime()

    class BrokenFinal:
        def __init__(self, engine, audit):
            self.audit = audit

        def run(self, request):
            self.audit.create(SimpleNamespace(investigation_id=uuid4()))
            raise RuntimeError("final commit failed")

    runtime.workflow_factory = BrokenFinal
    try:
        item = runtime.submit(uuid4(), payload())
        delegate.commit.set()
        wait_until(lambda: item.committed_id is not None)
        assert item.accept()
        wait_until(lambda: not item.worker_active)
        assert item.error == "execution_unconfirmed"
        assert runtime.execution(item.committed_id) == "unconfirmed"
    finally:
        runtime.close()
