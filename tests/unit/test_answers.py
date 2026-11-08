"""Readable explanations must preserve evidence strength, numbers and scenario semantics."""

from copy import deepcopy
from uuid import uuid4

import pytest

from bottleneck_analyzer.agents.contracts import KnowledgeOutput, SimulationOutput
from bottleneck_analyzer.domain.enums import QuestionIntent
from bottleneck_analyzer.domain.models import ScenarioRequest
from bottleneck_analyzer.retrieval.contracts import Diagnostics, EvidenceAssessment, RetrievalResult
from bottleneck_analyzer.workflows.answers import answer_paragraphs, experiment, maintenance, number

from .test_retrieval import item, request


def simulation(gain=3.353111, ci=(3.27521, 3.43101), moved=False):
    def stats(mean, interval):
        return dict(
            n=20,
            mean=mean,
            stdev=0.1,
            min=mean - 1,
            max=mean + 1,
            ci95=interval,
            interval_method="paired t",
        )

    return SimulationOutput(
        baseline=stats(46.255889, (46.2, 46.3)),
        scenario=stats(46.255889 + gain, (46.255889 + gain - 0.1, 46.255889 + gain + 0.1)),
        paired_gain=stats(gain, ci),
        comparison={},
        constraint_assessment={
            "baseline_constraint": {"primary": "Hemming"},
            "scenario_constraint": {"primary": "Framing" if moved else "Hemming"},
            "constraint_moved": moved,
        },
        seeds=list(range(20)),
        configuration_version="fixture",
        days=30,
        limitations=[],
    )


@pytest.mark.parametrize(
    "method,words",
    [
        ("repair_duration", "repair times"),
        ("failure_rate", "failure rate"),
    ],
)
def test_scenario_answers_lead_with_change_keep_uncertainty_and_full_data(method, words):
    result = simulation()
    before = deepcopy(result.model_dump())
    scenario = ScenarioRequest(target_station="Hemming", method=method, reduction_percentage=30)
    text = "\n".join(
        answer_paragraphs(QuestionIntent.WHAT_IF, None, simulation=result, scenario=scenario)
    )
    assert words in text.split(", the simulation")[0]
    assert text.startswith("With robot repair times") or text.startswith(
        "With the robot failure rate"
    )
    assert "46.26 to 49.61" in text and "3.35 extra bodies per hour" in text
    assert "Hemming would still be the main bottleneck" in text
    assert "20 paired runs of 30 days" in text and "3.28 to 3.43" in text
    assert "Historical output:" not in text and "False" not in text
    assert result.model_dump() == before


def test_no_invented_method_movement_or_clear_gain():
    result = simulation(gain=0, ci=(-0.1, 0.1), moved=True)
    lines = experiment(result, None)
    assert lines[0].startswith("Under the tested change")
    assert "repair" not in lines[0] and "30%" not in lines[0]
    assert any("from Hemming to Framing" in line for line in lines)
    assert any("don't establish a clear output improvement" in line for line in lines)
    result.constraint_assessment = {}
    assert "doesn't clearly establish" in experiment(result, None)[1]


def knowledge(label="supported_hypothesis", cause=None, available=True):
    evidence = item(recorded_cause=cause)
    assessment = EvidenceAssessment(
        station="Hemming",
        label=label,
        statement="Fixture assessment",
        evidence_ids=[evidence.evidence_id] if available else [],
        conflicting_evidence_ids=[],
        warnings=[],
    )
    return KnowledgeOutput(
        retrieval=RetrievalResult(
            dataset_id=uuid4(),
            dataset_name="fixture",
            provenance="authored_fixture",
            content_hash="fixture",
            request=request(),
            evidence=[evidence] if available else [],
            assessments=[assessment],
            diagnostics=Diagnostics(),
        ),
        interpretations=[],
    )


def test_maintenance_answer_explains_evidence_without_generic_production_summary():
    data = knowledge()
    before = deepcopy(data.model_dump())
    text = "\n".join(answer_paragraphs(QuestionIntent.CAUSES, None, data))
    assert text.startswith("The maintenance evidence at Hemming")
    assert "doesn't confirm a specific cause" in text
    assert "don't yet identify the failed component" in text
    assert "confirmed root cause" in text and "lead to investigate" in text
    for internal in ["supported_hypothesis", "Historical output:", "Design gap:", "Unresolved:"]:
        assert internal not in text
    assert "connector" not in text  # Never invent a component diagnosis from a relevant note.
    assert data.model_dump() == before


def test_robot_fault_description_requires_supporting_fault_and_work_order_records():
    data = knowledge()
    fault = item(
        source_system="SCADA",
        source_type="fault_event",
        text="robot_fault robot",
        recorded_cause=None,
    )
    data.retrieval.evidence.append(fault)
    data.retrieval.assessments[0].evidence_ids.append(fault.evidence_id)
    text = "\n".join(maintenance(data))
    assert text.startswith("The records suggest that robot faults and repairs")
    assert "linked maintenance work orders" in text and "at Hemming" in text
    fault.text = "conveyor_fault conveyor"
    assert "robot faults" not in "\n".join(maintenance(data))


@pytest.mark.parametrize(
    "label", ["insufficient_evidence", "observed_association", "recorded_maintenance_cause"]
)
def test_other_evidence_strengths_remain_distinct(label):
    data = knowledge(
        label, cause="Damaged connector" if label == "recorded_maintenance_cause" else None
    )
    text = "\n".join(maintenance(data))
    if label == "recorded_maintenance_cause":
        assert "explicitly report: Damaged connector" in text
    elif label == "observed_association":
        assert "isn't enough to establish the cause" in text
    else:
        assert "couldn't find enough" in text
    assert label not in text


def test_missing_records_failed_search_and_long_cause_do_not_overclaim():
    data = knowledge(available=False)
    data.retrieval.diagnostics.unavailable = {"semantic": "provider unavailable"}
    text = "\n".join(maintenance(data))
    assert "couldn't find enough" in text and "check is incomplete" in text
    data = knowledge("recorded_maintenance_cause", cause="x" * 2000)
    assert len(maintenance(data)[0]) < 1600
    assert "full descriptions" in maintenance(data)[0]


@pytest.mark.parametrize(
    "value,expected",
    [
        (46.8800, "46.88"),
        (21096, "21,096"),
        (450, "450"),
        (0, "0"),
        (0.0001, "0.0001"),
        (-3.353111, "-3.35"),
    ],
)
def test_display_numbers_are_readable_without_changing_stored_values(value, expected):
    assert number(value) == expected


def test_model_filtered_output_does_not_become_exclusive_line_capacity():
    from bottleneck_analyzer.agents.contracts import AnalyticsSummary

    from .test_api import audit_row

    historical = AnalyticsSummary.model_validate(audit_row()["response"]["historical"])
    historical.scope.model = "SUV"
    historical.design_gap_jph = None
    text = "\n".join(answer_paragraphs(QuestionIntent.CONSTRAINT_OUTPUT_LOSS, historical))
    assert "For SUV, the records show" in text
    assert "share of mixed-line output" in text
    assert "design reference" not in text
