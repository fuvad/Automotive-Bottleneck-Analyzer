"""Shared deterministic checks and response projection, not an additional agent."""

import math

from bottleneck_analyzer.agents.contracts import (
    AnalyticsSummary,
    InvestigationPlan,
    SegmentSummary,
    WorkflowState,
)
from bottleneck_analyzer.agents.planner import WORKFLOWS
from bottleneck_analyzer.simulation.config import Intervention, SimulationConfig, updated
from bottleneck_analyzer.workflows.answers import comparisons, source_excerpts


def validate_plan(plan: InvestigationPlan) -> None:
    if tuple(plan.agents) != WORKFLOWS[plan.intent]:
        raise ValueError("Plan does not match the predefined workflow registry")
    if ("simulation" in plan.agents) != (plan.scenario is not None):
        raise ValueError("Scenario presence does not match the registered workflow")


def validate_results(state: WorkflowState) -> None:
    if state.plan is None or state.analytics is None:
        raise ValueError("Required analytics results are missing")
    validate_plan(state.plan)
    analytics = state.analytics
    if (
        analytics.dataset_id != state.context.dataset_id
        or analytics.content_hash != state.context.content_hash
        or analytics.scope != state.scope
    ):
        raise ValueError("Analytics identity or scope changed")
    line = analytics.overall.line
    expected = line.completed / line.scheduled_hours if line.scheduled_hours else None
    if expected is None:
        if line.jph is not None:
            raise ValueError("Closed period must not report JPH")
    elif line.jph is None or not math.isclose(line.jph, expected, abs_tol=1e-9):
        raise ValueError("Historical JPH denominator failed validation")
    if analytics.overall.model is not None:
        if line.design_gap_jph is not None:
            raise ValueError("Model contribution must not be treated as exclusive line capacity")
    elif expected is not None and (
        line.design_gap_jph is None
        or not math.isclose(line.design_gap_jph, line.design_rate_jph - expected, abs_tol=1e-9)
    ):
        raise ValueError("Design gap failed validation")
    if "knowledge" in state.plan.agents:
        if state.knowledge is None:
            raise ValueError("Required evidence result is missing")
        evidence = state.knowledge.retrieval
        if (
            evidence.dataset_id != analytics.dataset_id
            or evidence.content_hash != analytics.content_hash
            or evidence.request.start_time != analytics.overall.start_time
            or evidence.request.end_time != analytics.overall.end_time
        ):
            raise ValueError("Evidence identity or period differs from analytics")
        ids = {e.evidence_id for e in evidence.evidence}
        for assessment in evidence.assessments:
            if set(assessment.evidence_ids + assessment.conflicting_evidence_ids) - ids:
                raise ValueError("Assessment cites evidence absent from the result")
    if "simulation" in state.plan.agents:
        if state.simulation is None:
            raise ValueError("Required simulation result is missing")
        result = state.simulation
        data = result.comparison
        scenario = state.plan.scenario
        configuration = state.context.simulation_config
        if scenario is None or configuration is None:
            raise ValueError("Simulation configuration missing")
        target = scenario.request.target_station
        if target == "candidate":
            target = analytics.overall.leading_candidate
        baseline = updated(
            configuration, days=scenario.days or configuration.days, record_history=False
        )
        expected_scenario = updated(
            baseline,
            intervention=Intervention(
                station=target,
                category=scenario.request.fault_category,
                method=scenario.request.method,
                reduction_percentage=scenario.request.reduction_percentage,
            ),
        )
        if (
            SimulationConfig.model_validate(data["baseline_config"]) != baseline
            or SimulationConfig.model_validate(data["scenario_config"]) != expected_scenario
        ):
            raise ValueError("Simulation changed non-target parameters or scenario semantics")
        expected_seeds = list(
            range(scenario.seed_start, scenario.seed_start + scenario.replications)
        )
        if result.seeds != expected_seeds or result.days != baseline.days:
            raise ValueError("Simulation did not preserve requested seeds or horizon")
        if not math.isclose(
            result.scenario.mean - result.baseline.mean, result.paired_gain.mean, abs_tol=1e-9
        ):
            raise ValueError("Simulation paired gain failed validation")
        if result.seeds != data["seeds"] or result.baseline.n != len(result.seeds):
            raise ValueError("Simulation seeds or replication count differ")
        if (
            data["baseline"] != result.baseline.model_dump(mode="json")
            or data["scenario"] != result.scenario.model_dump(mode="json")
            or data["paired_gain"] != result.paired_gain.model_dump(mode="json")
        ):
            raise ValueError("Simulation summary differs from its tool results")
        assessment = result.constraint_assessment
        for key in ("baseline", "scenario", "paired_gain"):
            if assessment[key] != data[key]:
                raise ValueError("Constraint assessment belongs to another comparison")
        for key in ("baseline_constraint", "scenario_constraint"):
            sensitivity = assessment[key]
            if sensitivity["days"] != min(scenario.sensitivity_days, baseline.days) or sensitivity[
                "seeds"
            ] != list(
                range(
                    scenario.sensitivity_seed_start,
                    scenario.sensitivity_seed_start + scenario.sensitivity_replications,
                )
            ):
                raise ValueError("Constraint assessment uses unexpected scope or seeds")


def summarize(state: WorkflowState) -> AnalyticsSummary | None:
    result = state.analytics
    if result is None:
        return None
    overall = result.overall
    candidate = next(
        (c for c in overall.candidates if c.station == overall.leading_candidate), None
    )
    return AnalyticsSummary(
        dataset_id=result.dataset_id,
        content_hash=result.content_hash,
        scope=result.scope,
        leading_candidate=overall.leading_candidate,
        historical_jph=overall.line.jph,
        design_gap_jph=overall.line.design_gap_jph,
        scheduled_hours=overall.line.scheduled_hours,
        completed=overall.line.completed,
        evidence_strength=candidate.strength if candidate else "insufficient_evidence",
        supporting_indicators=candidate.supporting_evidence if candidate else [],
        conflicting_indicators=candidate.contradicting_evidence if candidate else [],
        aggregate_ids=candidate.aggregate_ids if candidate else [],
        candidate_changes=result.candidate_changes,
        segments=[
            SegmentSummary(
                key=s.key,
                kind=s.kind,
                label=s.label,
                jph=s.line.jph,
                completed=s.line.completed,
                scheduled_hours=s.line.scheduled_hours,
                leading_candidate=s.leading_candidate,
                warnings=s.warnings,
            )
            for s in result.segments
        ],
    )


def segmentation_findings(summary: AnalyticsSummary) -> list[str]:
    """Compatibility entry point for presentation of the existing segment results."""
    return comparisons(summary)


def render(state: WorkflowState, answer: str) -> str:
    """Preserve Agent 1's complete validated answer without adding category paragraphs."""
    return "\n\n".join(
        [
            answer,
            *source_excerpts(state.knowledge),
            "Human review and approval are required before any operational change.",
        ]
    )
