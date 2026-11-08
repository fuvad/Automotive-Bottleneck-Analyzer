"""Plain-language presentation of validated findings; no tools or new calculations."""

from collections import Counter

from bottleneck_analyzer.agents.contracts import (
    AnalyticsSummary,
    KnowledgeOutput,
    SimulationOutput,
)
from bottleneck_analyzer.domain.enums import QuestionIntent
from bottleneck_analyzer.domain.models import ScenarioRequest


def number(value: float | int | None) -> str:
    if value is None:
        return "unavailable"
    precision = 4 if 0 < abs(value) < 0.01 else 2
    return f"{value:,.{precision}f}".rstrip("0").rstrip(".")


def comparisons(summary: AnalyticsSummary) -> list[str]:
    lines = []
    for kind, label in (("shift", "dated shifts"), ("utc_hour", "UTC-hour groups")):
        segments = [s for s in summary.segments if s.kind == kind]
        if not segments:
            continue
        counts = Counter(s.leading_candidate for s in segments if s.leading_candidate)
        resolved = sum(counts.values())
        if not counts:
            lines.append(
                f"There isn't enough evidence to identify a bottleneck across the {label}."
            )
        elif len(counts) == 1:
            candidate = next(iter(counts))
            if resolved == len(segments):
                lines.append(
                    f"The result is consistent across all {resolved} {label}: "
                    f"{candidate} is the leading bottleneck candidate."
                )
            else:
                lines.append(
                    f"{candidate} is the leading candidate in all {resolved} {label} "
                    "where the evidence is clear enough to name one."
                )
        else:
            lines.append(
                f"The likely bottleneck changes across the {label}: "
                + "; ".join(
                    f"{candidate} leads in {count}" for candidate, count in sorted(counts.items())
                )
                + "."
            )
        if resolved < len(segments):
            lines.append(
                f"The remaining {len(segments) - resolved} {label} are inconclusive, "
                "so I wouldn't assume they have the same bottleneck."
            )
    models = [s for s in summary.segments if s.kind == "model"]
    if models:
        names = ", ".join(s.label for s in models)
        candidates = {s.leading_candidate for s in models}
        if len(candidates) == 1 and None not in candidates and len(models) > 1:
            lines.append(
                f"{names} point to the same model-specific candidate: "
                f"{next(iter(candidates))}. There is no difference between them "
                "in the reported candidate."
            )
        else:
            lines.append(
                "For the vehicle models, "
                + "; ".join(
                    f"{s.label} points to {s.leading_candidate}"
                    if s.leading_candidate
                    else f"{s.label} has no clear candidate"
                    for s in models
                )
                + "."
            )
        lines.append(
            "The model rates describe each model's share of mixed-line output, not how fast "
            "the line would run making that model alone. Machine-state time is shared across "
            "models, so these results don't prove a separate physical bottleneck for each model."
        )
    return lines or [
        "There aren't any segment results to compare, so I can't tell whether "
        "the bottleneck changes by shift, model or time of day."
    ]


def maintenance(knowledge: KnowledgeOutput | None) -> list[str]:
    if knowledge is None:
        return ["I don't have a maintenance-evidence result to explain these interruptions."]
    records = {e.evidence_id: e for e in knowledge.retrieval.evidence}
    lines = []
    for assessment in knowledge.retrieval.assessments:
        station = assessment.station
        support = [records[i] for i in assessment.evidence_ids if i in records]
        if assessment.label == "recorded_maintenance_cause" and support:
            causes = list(dict.fromkeys(e.recorded_cause for e in support if e.recorded_cause))
            if causes and len("; ".join(causes)) <= 600:
                lines.append(
                    f"Maintenance records at {station} explicitly report: "
                    + "; ".join(causes)
                    + ". This is what maintenance recorded; "
                    "it doesn't establish how much line output the issue cost."
                )
            elif causes:
                lines.append(
                    f"Maintenance has recorded a cause for incidents at {station}. "
                    "The full descriptions are in the work orders under View evidence. "
                    "They don't establish how much line output the issue cost."
                )
            else:
                lines.append(
                    f"The maintenance assessment for {station} reports: " + assessment.statement
                )
        elif assessment.label == "supported_hypothesis" and support:
            faults = [e for e in support if e.source_type == "fault_event"]
            work_orders = [e for e in support if e.source_type == "maintenance_work_order"]
            if faults and work_orders:
                kind = (
                    "robot faults"
                    if any("robot_fault" in e.text.casefold() for e in faults)
                    else "equipment faults"
                )
                lines.append(
                    f"The records suggest that {kind} and repairs may explain some "
                    f"of the interruptions at {station}. The supporting evidence "
                    "includes fault logs and linked maintenance work orders."
                )
            else:
                lines.append(
                    f"The maintenance evidence at {station} suggests equipment problems "
                    "may be related to the stops, but it doesn't confirm a specific cause."
                )
            lines.append(
                "They don't yet identify the failed component or show how much of "
                "the line's lost output came from these interruptions. I'd treat this "
                "as a lead to investigate, rather than a confirmed root cause."
            )
        elif assessment.label == "observed_association" and support:
            lines.append(
                f"I found records linked to {station} in this period, but they don't "
                "provide a clear explanation for the interruptions. A match in "
                "station, time or incident isn't enough to establish the cause."
            )
        else:
            lines.append(
                f"I couldn't find enough usable maintenance evidence to explain "
                f"the interruptions at {station}."
            )
        if assessment.conflicting_evidence_ids:
            lines.append(
                "Some retrieved records conflict with the explanation or were excluded "
                "from it. Their details and limitations are available in View evidence."
            )
    if not lines:
        lines.append(
            "The search didn't produce a usable cause assessment, so I can't "
            "reliably explain the interruptions from these records."
        )
    if knowledge.retrieval.diagnostics.unavailable:
        lines.append("Some evidence searches were unavailable, so this check is incomplete.")
    return lines


def experiment(result: SimulationOutput | None, scenario: ScenarioRequest | None) -> list[str]:
    if result is None:
        return ["I don't have a simulation result for that change, so I can't estimate its effect."]
    action = "Under the tested change"
    if scenario and scenario.method:
        equipment = "robot " if scenario.fault_category == "robot_fault" else ""
        method = (
            f"{equipment}repair times"
            if scenario.method == "repair_duration"
            else f"the {equipment}failure rate"
        )
        target = scenario.target_station
        if target == "candidate":
            target = (
                (result.comparison.get("scenario_config") or {}).get("intervention") or {}
            ).get("station") or "the target station"
        action = f"With {method} at {target} reduced by {number(scenario.reduction_percentage)}%"
    gain = result.paired_gain
    change = f"an average change of {number(gain.mean)} bodies per hour"
    if gain.mean > 0:
        change = f"about {number(gain.mean)} extra bodies per hour"
    lines = [
        f"{action}, the simulation estimates output would go from "
        f"{number(result.baseline.mean)} to {number(result.scenario.mean)} bodies per hour — "
        f"{change}."
    ]
    assessment = result.constraint_assessment
    before = (assessment.get("baseline_constraint") or {}).get("primary")
    after = (assessment.get("scenario_constraint") or {}).get("primary")
    moved = assessment.get("constraint_moved")
    if before and after and before == after and moved is False:
        lines.append(
            f"{after} would still be the main bottleneck in this model. "
            "The tested change doesn't move the bottleneck to another station."
        )
    elif before and after and before != after and moved is True:
        lines.append(f"The model suggests the bottleneck would move from {before} to {after}.")
    else:
        lines.append("The model doesn't clearly establish whether the bottleneck would move.")
    lines.append(
        f"This estimate comes from {gain.n} paired runs of {result.days} days each. "
        f"The 95% confidence interval for the output change is {number(gain.ci95[0])} to "
        f"{number(gain.ci95[1])} bodies per hour. It describes variation between simulation "
        "runs, not a guarantee of the result in a real plant."
    )
    if gain.ci95[0] <= 0 <= gain.ci95[1]:
        lines.append(
            "That interval includes zero, so these runs don't establish a clear output improvement."
        )
    return lines


def answer_paragraphs(
    intent: QuestionIntent | None,
    historical: AnalyticsSummary | None,
    knowledge: KnowledgeOutput | None = None,
    simulation: SimulationOutput | None = None,
    scenario: ScenarioRequest | None = None,
) -> list[str]:
    """Select relevant, bounded wording; all numbers come from supplied tool results."""
    if intent == QuestionIntent.CAUSES:
        return maintenance(knowledge)
    if intent == QuestionIntent.WHAT_IF:
        return experiment(simulation, scenario)
    if intent == QuestionIntent.SEGMENTATION:
        return (
            comparisons(historical) if historical else ["I don't have segment results to compare."]
        )
    if historical is None:
        return ["I don't have validated historical measurements for this question."]
    candidate = historical.leading_candidate
    lines = [
        f"The historical data point to {candidate} as the most likely bottleneck for this period."
        if candidate
        else "The available data don't point clearly to a single bottleneck."
    ]
    if intent == QuestionIntent.COMBINED:
        return lines + maintenance(knowledge) + experiment(simulation, scenario)
    if historical.historical_jph is not None:
        subject = (
            f"For {historical.scope.model}, the records show"
            if historical.scope.model
            else "The line completed"
        )
        lines.append(
            f"{subject} {number(historical.completed)} bodies over "
            f"{number(historical.scheduled_hours)} scheduled hours — "
            f"{number(historical.historical_jph)} bodies per hour."
        )
        if historical.scope.model:
            lines.append(
                "That rate is this model's share of mixed-line output, not the "
                "line's capacity if it made only this model."
            )
    else:
        lines.append(
            "There were no scheduled production hours in this period, so an hourly "
            "output rate isn't available."
        )
    if historical.design_gap_jph is not None:
        lines.append(
            f"The gap to the design reference is {number(historical.design_gap_jph)} "
            "bodies per hour. That isn't the amount a single fix would necessarily recover."
        )
    lines.append(
        "This is a historical indication; it still needs confirmation before changing "
        "the production process."
    )
    return lines


def source_excerpts(knowledge: KnowledgeOutput | None) -> list[str]:
    """Keep verbatim source citations available to non-browser consumers and audits."""
    return (
        [
            f"[{excerpt.evidence_id}] {excerpt.quote}"
            for item in knowledge.interpretations
            for excerpt in item.excerpts
        ]
        if knowledge
        else []
    )
