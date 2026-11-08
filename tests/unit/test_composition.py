"""Question-specific writing, bounded context and numerical/source reference safeguards."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from bottleneck_analyzer.agents.composition import (
    CompositionDraft,
    CompositionPart,
    check_wording,
    composition_facts,
)
from bottleneck_analyzer.agents.contracts import (
    ConversationTurn,
    InvestigationRequest,
    WorkflowState,
)
from bottleneck_analyzer.agents.planner import PlannerAgent
from bottleneck_analyzer.analytics.contracts import Candidate
from bottleneck_analyzer.domain.enums import QuestionIntent
from bottleneck_analyzer.workflows.validation import render
from tests.composition_fixtures import draft_parts

from .test_orchestration import bundle as bundle


def state_for(bundle, question):
    scope, context, analytics = bundle
    analytics.overall.leading_candidate = "Hemming"
    analytics.overall.candidates = [
        Candidate(
            station="Hemming",
            rank=1,
            score=0.9,
            indicators={},
            strength="strong",
            operations=100,
            state_coverage=1,
            supporting_evidence=["Input queue accumulation: 0.9826", "Upstream blocking: 0.2667"],
            contradicting_evidence=[],
            explanation="Synthetic fixture",
            aggregate_ids=[],
        )
    ]
    request = InvestigationRequest(question=question, scope=scope)
    return WorkflowState(
        question=question,
        request=request,
        scope=scope,
        context=context,
        analytics=analytics,
        intent=QuestionIntent.CONSTRAINT_OUTPUT_LOSS,
    )


class QuestionWriter:
    def __init__(self):
        self.inputs = []

    def generate(self, instruction, data, schema):
        self.inputs.append(data)
        if "what data" in data["question"].lower():
            return schema(
                answer_goal="Explain the station-specific evidence supporting the candidate.",
                paragraphs=draft_parts(
                    "Vehicles queue before Hemming and earlier stations are blocked. "
                    "Those observations support Hemming as a candidate, without proving it."
                ),
                fact_ids=["historical.support.0", "historical.support.1", "limits.historical"],
                evidence_ids=[],
                limitations=[],
            )
        return schema(
            answer_goal="Identify the candidate and quantify the output gap.",
            paragraphs=draft_parts(
                "The historical candidate is Hemming. Output is {{historical.rate}} "
                "and the gap to the design reference is {{historical.design_gap}}."
            ),
            fact_ids=["historical.candidate", "historical.rate", "historical.design_gap"],
            evidence_ids=[],
            limitations=[],
        )


@pytest.mark.parametrize(
    "part",
    [
        {"text": "Output is 46.88 bodies per hour."},
        {"text": "Output is \u2074\u2076.\u2078\u2078 bodies per hour."},
        {"text": "Output {{historical.rate}}"},
        {"text": ""},
        {},
        {"text": "Output", "quantity": "historical.rate"},
    ],
)
def test_draft_parts_reject_numeric_prose_and_ambiguous_parts(part):
    with pytest.raises(ValueError):
        TypeAdapter(CompositionPart).validate_python(part)


def test_paragraphs_preserve_natural_prose_and_code_owned_quantity_references():
    draft = CompositionDraft(
        answer_goal="Explain output.",
        fact_ids=["historical.rate"],
        evidence_ids=[],
        paragraphs=draft_parts("Output is {{historical.rate}}.\n\nThis is historical."),
        limitations=[],
    )
    assert draft.referenced_summary() == ("Output is {{historical.rate}}.\n\nThis is historical.")


def test_same_intent_and_facts_allow_different_answers_to_the_actual_questions(bundle):
    writer = QuestionWriter()
    agent = PlannerAgent(writer)
    first = state_for(bundle, "Which station is the strongest historical candidate and output gap?")
    answer = agent.explain(first, [])
    followup = state_for(bundle, "What data show that Hemming is the strongest bottleneck?")
    followup.conversation_context = [
        ConversationTurn(
            investigation_id=uuid4(),
            question=first.question,
            answer=answer.summary,
            scope=first.scope,
            outcome="completed",
            leading_candidate="Hemming",
        )
    ]
    explanation = agent.explain(followup, [])
    assert explanation.summary != answer.summary
    assert "10 bodies per hour" in answer.summary and "50 bodies per hour" in answer.summary
    assert explanation.summary.startswith("Vehicles queue")
    assert "Output is" not in explanation.summary
    assert writer.inputs[0]["facts"] == writer.inputs[1]["facts"]
    assert writer.inputs[1]["previous_exchanges"][0]["answer"] == answer.summary
    assert writer.inputs[1]["question"] == followup.question
    assert writer.inputs[1]["scope"] == followup.scope.model_dump(mode="json")
    assert explanation.composition_version == "question_specific_v1"
    text = render(followup, explanation.summary)
    assert text.startswith(explanation.summary)
    assert "The line completed" not in text and "gap to the design reference" not in text


@pytest.mark.parametrize(
    "text,selected,cited",
    [
        ("Output is 99 bodies per hour.", ["historical.rate"], []),
        ("Output is {{made_up_rate}}.", ["historical.rate"], []),
        ("Output is {{historical.rate}}.", ["historical.candidate"], []),
        ("Claim.", ["invented.fact"], []),
        ("Claim.", [], []),
        ("Claim.", ["historical.candidate"], ["invented.source"]),
        ("Claim {{broken.", ["historical.candidate"], []),
        ("Output {historical.rate}.", ["historical.rate"], []),
    ],
)
def test_unvalidated_quantities_facts_and_sources_are_rejected(bundle, text, selected, cited):
    facts = composition_facts(state_for(bundle, "Explain the candidate"))
    with pytest.raises(ValueError):
        check_wording(text, selected, cited, facts)


def test_simulation_numeric_claims_must_include_interval_and_use_code_formatted_units():
    facts = {
        "simulation.gain": {"text": "Gain", "value": "3.35 bodies per hour", "evidence_ids": []},
        "simulation.gain_interval": {
            "text": "Interval",
            "value": "3.28 to 3.43 bodies per hour (95% confidence interval)",
            "evidence_ids": [],
        },
    }
    with pytest.raises(ValueError, match="uncertainty"):
        check_wording("Gain: {{simulation.gain}}.", ["simulation.gain"], [], facts)
    text = check_wording(
        "Gain: {{simulation.gain}}; {{simulation.gain_interval}}.", list(facts), [], facts
    )
    assert "3.35 bodies per hour" in text and "95% confidence interval" in text


def test_existing_source_must_also_belong_to_a_selected_fact():
    facts = {
        "one": {"text": "Work order", "value": None, "evidence_ids": ["source-a"]},
        "two": {"text": "Different work order", "value": None, "evidence_ids": ["source-b"]},
    }
    with pytest.raises(ValueError):
        check_wording(
            "The maintenance record suggests a possible cause.", ["one"], ["source-b"], facts
        )


def test_source_citations_are_derived_from_selected_facts_not_generated_by_the_model(bundle):
    from .test_answers import knowledge

    state = state_for(bundle, "What maintenance evidence is available?")
    state.knowledge = knowledge()

    class SourceWriter:
        def generate(self, instruction, data, schema):
            assert all("evidence_ids" not in fact for fact in data["facts"].values())
            return schema(
                answer_goal="Explain the available maintenance evidence.",
                fact_ids=["evidence.assessment.0"],
                evidence_ids=[],
                limitations=[],
                paragraphs=draft_parts(
                    "The records suggest a possible explanation, not a confirmed cause."
                ),
            )

    expected = state.knowledge.retrieval.assessments[0].evidence_ids
    result = PlannerAgent(SourceWriter()).explain(state, expected)
    assert result.evidence_ids == expected


def test_failed_composition_reports_the_guard_reason_without_exposing_the_bad_draft(
    monkeypatch, bundle
):
    from .test_orchestration import make_workflow

    workflow, request = make_workflow(monkeypatch, bundle)
    original = workflow.planner.llm.generate

    def invalid(instruction, data, schema):
        output = original(instruction, data, schema)
        if schema.__name__ == "GroundedExplanation":
            output.paragraphs = schema(
                answer_goal="Quantify output.",
                fact_ids=["historical.rate"],
                evidence_ids=[],
                limitations=[],
                paragraphs=draft_parts("The output was {{historical.design_gap}}."),
            ).paragraphs
            output.fact_ids = ["historical.rate"]
        return output

    workflow.planner.llm.generate = invalid
    response = workflow.run(request)
    assert response.outcome == "failed"
    assert response.errors[-1].category == "CompositionValidationError"
    assert "could not be matched to the computed results" in response.answer
    assert "historical.design_gap" not in response.answer


def test_fact_catalogue_does_not_modify_results_or_offer_normalized_scores_as_percentages(bundle):
    state = state_for(bundle, "What evidence supports the candidate?")
    before = deepcopy(state.model_dump())
    facts = composition_facts(state)
    assert "0.9826" not in str(facts) and "0.2667" not in str(facts)
    assert "Input queue accumulation" in facts["historical.support.0"]["text"]
    assert facts["historical.rate"]["value"] == "10 bodies per hour"
    assert state.model_dump() == before


def test_exact_computed_values_with_units_are_accepted_without_new_calculations(bundle):
    facts = composition_facts(state_for(bundle, "What is the output?"))
    assert check_wording("Output is 10 bodies per hour.", ["historical.rate"], [], facts) == (
        "Output is 10 bodies per hour."
    )
    assert (
        check_wording(
            "Output is {{historical.rate}} (10 bodies per hour).", ["historical.rate"], [], facts
        )
        == "Output is 10 bodies per hour."
    )
    with pytest.raises(ValueError):
        check_wording("Output is 11 bodies per hour.", ["historical.rate"], [], facts)
    with pytest.raises(ValueError):
        check_wording("Output is 10 vehicles per minute.", ["historical.rate"], [], facts)


def test_one_malformed_draft_can_be_corrected_without_a_template_fallback(bundle):
    class RepairingWriter(QuestionWriter):
        def generate(self, instruction, data, schema):
            if "correction" not in data:
                self.inputs.append(data)
                return schema(
                    answer_goal="Quantify the recorded output.",
                    paragraphs=draft_parts("Output is {{historical.design_gap}}."),
                    fact_ids=["historical.rate"],
                    evidence_ids=[],
                    limitations=[],
                )
            assert "quantity placeholder" in data["correction"]["problem"]
            return super().generate(instruction, data, schema)

    writer = RepairingWriter()
    result = PlannerAgent(writer).explain(state_for(bundle, "Which station and output gap?"), [])
    assert len(writer.inputs) == 2
    assert "99" not in result.summary and "10 bodies per hour" in result.summary


def test_repeated_bad_drafts_fail_after_one_correction(bundle):
    class BadWriter:
        calls = 0

        def generate(self, instruction, data, schema):
            self.calls += 1
            return schema(
                answer_goal="Quantify the recorded output.",
                paragraphs=draft_parts("Output is {{historical.design_gap}}."),
                fact_ids=["historical.rate"],
                evidence_ids=[],
                limitations=[],
            )

    writer = BadWriter()
    with pytest.raises(ValueError):
        PlannerAgent(writer).explain(state_for(bundle, "Which station?"), [])
    assert writer.calls == 2


@pytest.mark.parametrize(
    "claim",
    [
        "These observations prove the physical constraint.",
        "These records confirm the root cause.",
        "This is a proven physical bottleneck.",
    ],
)
def test_historical_signals_cannot_be_promoted_to_proof(bundle, claim):
    facts = composition_facts(state_for(bundle, "Why this candidate?"))
    with pytest.raises(ValueError, match="prove or confirm"):
        check_wording(claim, ["historical.candidate"], [], facts)
    assert check_wording(
        "These signals do not prove the physical constraint.", ["historical.candidate"], [], facts
    )
