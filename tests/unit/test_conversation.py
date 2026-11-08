"""Bounded audit context and planner handoff without a provider or database."""

from datetime import timedelta
from uuid import uuid4

import pytest

from bottleneck_analyzer.agents.contracts import InvestigationRequest
from bottleneck_analyzer.workflows.context import resolve_context

from .test_orchestration import bundle as bundle
from .test_orchestration import make_workflow


def row(context, scope, previous=None, **patch):
    identifier = uuid4()
    return {
        "id": identifier,
        "audit_id": str(identifier),
        "response_id": str(identifier),
        "dataset_id": context.dataset_id,
        "content_hash": context.content_hash,
        "scope": scope.model_dump(mode="json"),
        "question": "Which station limits output?",
        "answer": "Hemming is a historical candidate.\n\nDetailed evidence",
        "outcome": "completed",
        "leading_candidate": "Hemming",
        "historical_jph": 46,
        "previous_id": previous,
        **patch,
    }


def test_only_last_five_confirmed_exchanges_oldest_first(bundle):
    scope, context, _ = bundle
    rows, previous = {}, None
    for index in range(8):
        item = row(context, scope, previous, question=f"Question {index}")
        rows[item["id"]] = item
        previous = item["id"]
    turns, notices = resolve_context(previous, scope, context, rows.get)
    assert [t.question for t in turns] == [f"Question {i}" for i in range(3, 8)]
    assert turns[-1].leading_candidate == "Hemming" and not notices
    assert "\n\n" not in turns[-1].answer


@pytest.mark.parametrize(
    "patch",
    [
        {"audit_id": None},
        {"response_id": str(uuid4())},
        {"dataset_id": uuid4()},
        {"content_hash": "other"},
    ],
)
def test_missing_unconfirmed_or_cross_dataset_context_rejected(bundle, patch):
    scope, context, _ = bundle
    item = row(context, scope, **patch)
    with pytest.raises(ValueError):
        resolve_context(item["id"], scope, context, lambda _: item)
    with pytest.raises(ValueError):
        resolve_context(uuid4(), scope, context, lambda _: None)


def test_period_change_and_cycles(bundle):
    scope, context, _ = bundle
    item = row(context, scope)
    changed = scope.model_copy(update={"end_time": scope.end_time + timedelta(days=1)})
    turns, notices = resolve_context(item["id"], changed, context, lambda _: item)
    assert not turns and "period changed" in notices[0]
    item["previous_id"] = item["id"]
    with pytest.raises(ValueError, match="cycle"):
        resolve_context(item["id"], scope, context, lambda _: item)


@pytest.mark.parametrize("outcome", ["failed", "unsupported", "clarification_required"])
def test_non_factual_turns_keep_question_but_not_findings(bundle, outcome):
    scope, context, _ = bundle
    item = row(context, scope, outcome=outcome, clarification="Which method?")
    turns, _ = resolve_context(item["id"], scope, context, lambda _: item)
    assert turns[0].question == item["question"]
    assert turns[0].clarification == "Which method?"
    assert turns[0].leading_candidate is None and turns[0].historical_jph is None
    assert turns[0].scenario is None and not turns[0].evidence_labels
    assert turns[0].answer == ""


def test_followup_context_precedes_audit_and_reaches_existing_planner(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)
    scope, context, _ = bundle
    item = row(context, scope)
    turns, _ = resolve_context(item["id"], scope, context, lambda _: item)
    monkeypatch.setattr(
        "bottleneck_analyzer.workflows.graph.load_conversation", lambda *args: (turns, [])
    )
    original = workflow.planner.llm.generate
    captured = []

    def generate(instruction, data, schema):
        if "previous_exchanges" in data:
            captured.append(data)
        return original(instruction, data, schema)

    workflow.planner.llm.generate = generate
    workflow.run(
        InvestigationRequest(
            question="Why is that happening?",
            scope=request.scope,
            previous_investigation_id=item["id"],
        )
    )
    assert captured[0]["previous_exchanges"][0]["leading_candidate"] == "Hemming"
    assert captured[0]["question"] == "Why is that happening?"
    assert workflow.audit.create.call_args.args[0].conversation_context == turns


def test_bad_parent_does_not_create_a_new_audit(monkeypatch, bundle):
    workflow, request = make_workflow(monkeypatch, bundle)

    def unavailable(*args):
        raise ValueError("Previous investigation has no confirmed final response")

    monkeypatch.setattr("bottleneck_analyzer.workflows.graph.load_conversation", unavailable)
    request.previous_investigation_id = uuid4()
    with pytest.raises(ValueError):
        workflow.run(request)
    workflow.audit.create.assert_not_called()
