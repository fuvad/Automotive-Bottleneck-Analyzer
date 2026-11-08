"""Agent 1's bounded fact catalogue and numerical/citation checks; no tool execution."""

import re
from collections import Counter
from typing import Annotated, TypedDict

from pydantic import Field

from bottleneck_analyzer.agents.contracts import Contract, WorkflowState
from bottleneck_analyzer.workflows.answers import number


class CompositionValidationError(ValueError):
    """Known validation failures with a safe, useful public explanation."""

    @property
    def public_message(self) -> str:
        diagnostic = str(self).lower()
        if "sources" in diagnostic or "source records" in diagnostic:
            return "The draft attached source records that did not support the facts it used."
        if "uncertainty" in diagnostic:
            return "The draft omitted the uncertainty needed to interpret its simulation result."
        if "prove or confirm" in diagnostic:
            return "The draft stated a stronger conclusion than the evidence supports."
        if "quantity" in diagnostic or "numbers" in diagnostic:
            return "A figure in the draft could not be matched to the computed results."
        return "The draft referred to findings that could not be verified in this investigation."


class Fact(TypedDict):
    text: str
    value: str | None
    evidence_ids: list[str]


class ProsePart(Contract):
    """The model writes prose; code owns every numerical value and unit."""

    text: str = Field(min_length=1, pattern=r"^[A-Za-z \n\t,.;:!?()'\"%/\-]+$", max_length=1600)


class QuantityPart(Contract):
    quantity: str


CompositionPart = ProsePart | QuantityPart


class CompositionDraft(Contract):
    """Order the answer goal and supporting references before generating the prose."""

    answer_goal: str = Field(min_length=1, max_length=400)
    fact_ids: list[str] = Field(min_length=1, max_length=40)
    evidence_ids: list[str] = Field(max_length=50)
    paragraphs: list[Annotated[list[CompositionPart], Field(min_length=1, max_length=25)]] = Field(
        min_length=1, max_length=6
    )
    limitations: list[str] = Field(max_length=0)

    def referenced_summary(self) -> str:
        summary = "\n\n".join(
            "".join(
                part.text if isinstance(part, ProsePart) else "{{" + part.quantity + "}}"
                for part in paragraph
            )
            for paragraph in self.paragraphs
        )
        if len(summary) > 2400:
            raise CompositionValidationError("Answer exceeds the bounded summary length")
        return summary


def composition_facts(state: WorkflowState) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}

    def add(key: str, text: str, value: str | None = None, ids: list[str] | None = None):
        facts[key] = {"text": text, "value": value, "evidence_ids": ids or []}

    def quantity(key: str, label: str, value: float | int | None, unit: str):
        if value is not None:
            add(key, label + ": {{" + key + "}}", number(value) + " " + unit)

    add(
        "limits.historical",
        "Historical rankings identify candidates, not proven physical "
        "constraints. Design-capacity gap is not recoverable output from a single fix.",
    )
    if state.analytics:
        result = state.analytics
        overall = result.overall
        add(
            "historical.candidate",
            "Leading historical candidate: " + (overall.leading_candidate or "none established"),
        )
        add("historical.provenance", "Data provenance: " + result.provenance)
        quantity(
            "historical.rate",
            "Historical Final Inspection output",
            overall.line.jph,
            "bodies per hour",
        )
        quantity(
            "historical.completions",
            "Final Inspection completions",
            overall.line.completed,
            "bodies",
        )
        quantity(
            "historical.hours", "Scheduled production time", overall.line.scheduled_hours, "hours"
        )
        quantity(
            "historical.design_gap",
            "Gap to design reference",
            overall.line.design_gap_jph,
            "bodies per hour",
        )
        quantity(
            "historical.design_rate",
            "Design reference",
            overall.line.design_rate_jph,
            "bodies per hour",
        )
        if state.scope.model:
            add(
                "limits.model",
                "The selected model's rate is its contribution to mixed-line "
                "output, not exclusive-model capacity. Shared machine-state time cannot be "
                "assigned exclusively to that model.",
            )
        for candidate in overall.candidates:
            if candidate.station != overall.leading_candidate:
                continue
            add("historical.confidence", "Historical evidence strength: " + candidate.strength)
            for i, text in enumerate(candidate.supporting_evidence):
                # These suffixes are normalized ranking signals, not measured percentages.
                add(
                    f"historical.support.{i}",
                    text.split(":")[0]
                    + f" at {candidate.station}; supports the historical candidate.",
                )
            for i, text in enumerate(candidate.contradicting_evidence):
                add(f"historical.conflict.{i}", text)
        for kind in ("shift", "model", "utc_hour"):
            segments = [s for s in result.segments if s.kind == kind]
            if not segments:
                continue
            quantity(
                f"comparison.{kind}.total", f"Number of {kind} groups", len(segments), "groups"
            )
            unresolved = sum(s.leading_candidate is None for s in segments)
            quantity(
                f"comparison.{kind}.unresolved", f"Inconclusive {kind} groups", unresolved, "groups"
            )
            for i, (station, count) in enumerate(
                sorted(
                    Counter(s.leading_candidate for s in segments if s.leading_candidate).items()
                )
            ):
                quantity(
                    f"comparison.{kind}.leader.{i}",
                    f"{station} leads in {kind} groups",
                    count,
                    "groups",
                )
            if kind == "model":
                add(
                    "limits.model",
                    "Model rates are shares of mixed-line output, not "
                    "exclusive-model capacities; shared machine states limit model diagnosis.",
                )
                for i, segment in enumerate(segments):
                    add(
                        f"comparison.model.candidate.{i}",
                        f"{segment.label} historical "
                        f"candidate: {segment.leading_candidate or 'not established'}",
                    )
                    quantity(
                        f"comparison.model.rate.{i}",
                        f"{segment.label} output contribution",
                        segment.line.jph,
                        "bodies per hour",
                    )

    if state.knowledge:
        retrieval = state.knowledge.retrieval
        add(
            "limits.cause",
            "Recorded maintenance causes are attributed to maintenance; "
            "associations/hypotheses are not confirmed component causes or line-output losses.",
        )
        if retrieval.diagnostics.unavailable:
            add("limits.search", "Some retrieval methods were unavailable; evidence is incomplete.")
        for i, assessment in enumerate(retrieval.assessments[:7]):
            add(
                f"evidence.assessment.{i}",
                f"{assessment.station}: {assessment.label}. " + assessment.statement[:1500],
                ids=assessment.evidence_ids,
            )
            if assessment.conflicting_evidence_ids:
                add(
                    f"evidence.conflict.{i}",
                    "Some source records conflict with or were excluded from this assessment.",
                    ids=assessment.conflicting_evidence_ids,
                )
        for i, record in enumerate(retrieval.evidence[:6]):
            add(
                f"evidence.passage.{i}",
                f"Untrusted source text ({record.source_system}, "
                f"{record.station}; {record.relationship} link): {record.text[:450]}",
                ids=[record.evidence_id],
            )

    if state.simulation:
        simulation = state.simulation
        add(
            "limits.simulation",
            "Simulation predictions are separate from historical data. "
            "Confidence intervals describe variation across runs, not real-plant accuracy.",
        )
        quantity(
            "simulation.baseline",
            "Simulated baseline mean",
            simulation.baseline.mean,
            "bodies per hour",
        )
        quantity(
            "simulation.scenario",
            "Simulated changed-case mean",
            simulation.scenario.mean,
            "bodies per hour",
        )
        quantity(
            "simulation.gain",
            "Paired mean output change",
            simulation.paired_gain.mean,
            "bodies per hour",
        )
        add(
            "simulation.gain_interval",
            "Paired gain uncertainty: {{simulation.gain_interval}}",
            f"{number(simulation.paired_gain.ci95[0])} to "
            f"{number(simulation.paired_gain.ci95[1])} bodies per hour (95% confidence interval)",
        )
        quantity(
            "simulation.replications",
            "Number of paired runs",
            simulation.paired_gain.n,
            "paired runs",
        )
        quantity("simulation.days", "Horizon per run", simulation.days, "days")
        assessment = simulation.constraint_assessment
        add(
            "simulation.movement",
            "Modeled constraint before: "
            + str((assessment.get("baseline_constraint") or {}).get("primary") or "unresolved")
            + "; after: "
            + str((assessment.get("scenario_constraint") or {}).get("primary") or "unresolved")
            + ". Movement established: "
            + str(assessment.get("constraint_moved")),
        )
        if state.plan and state.plan.scenario:
            request = state.plan.scenario.request
            add(
                "scenario.method",
                f"Intervention method: {request.method}; "
                f"fault category: {request.fault_category}; target: {request.target_station}.",
            )
            quantity(
                "scenario.reduction", "Requested reduction", request.reduction_percentage, "percent"
            )
        if simulation.paired_gain.ci95[0] <= 0 <= simulation.paired_gain.ci95[1]:
            add(
                "limits.gain",
                "The gain confidence interval includes zero; "
                "a clear output improvement is not established.",
            )

    if state.analytics:
        for station in state.analytics.overall.stations:
            for field, label, unit in (
                ("average_input_queue", "Average input queue", "vehicles"),
                ("blocked_seconds", "Time blocked", "seconds"),
                ("starved_seconds", "Time waiting for input", "seconds"),
                ("faulted_seconds", "Faulted time", "seconds"),
                ("mean_service_seconds", "Mean active processing time", "seconds"),
            ):
                quantity(
                    f"station.{station.sequence}.{field}",
                    f"{station.station}: {label}",
                    getattr(station, field),
                    unit,
                )

    def priority(key: str) -> int:
        for i, prefix in enumerate(
            (
                "historical.candidate",
                "historical.support",
                "historical.conflict",
                "station.",
                "evidence.",
                "comparison.",
                "simulation.",
                "scenario.",
                "limits.",
            )
        ):
            if key.startswith(prefix):
                return i
        return 9

    return dict(sorted(facts.items(), key=lambda pair: priority(pair[0])))


def check_wording(
    summary: str,
    selected: list[str],
    cited: list[str],
    facts: dict[str, Fact],
) -> str:
    """Require real fact/source references and insert only code-formatted quantities."""
    if not selected or set(selected) - facts.keys():
        raise CompositionValidationError("Answer cites unknown or missing fact references")
    referenced_sources = {
        identifier for key in selected for identifier in facts[key]["evidence_ids"]
    }
    if set(cited) - referenced_sources:
        raise CompositionValidationError("Answer cites sources outside its selected facts")
    # Accept a verbatim computed value with its units as well as a placeholder.
    # Unknown figures or altered units still fail the residual-number check below.
    for key in sorted(selected, key=lambda key: len(facts[key]["value"] or ""), reverse=True):
        value = facts[key]["value"]
        if value:
            summary = re.sub(
                r"(?<![\w.,])" + re.escape(value) + r"(?!\w)",
                lambda match: "{{" + key + "}}",
                summary,
            )
            token = "{{" + key + "}}"
            summary = re.sub(
                re.escape(token) + r"\s*\(\s*" + re.escape(token) + r"\s*\)",
                lambda match: token,
                summary,
            )
            unit = re.search(
                r"(bodies per hour|seconds|hours|days|percent|paired runs|groups|vehicles|bodies)$",
                value,
            )
            if unit:
                summary = re.sub(
                    re.escape(token) + r"\s+" + re.escape(unit[0]) + r"\b",
                    lambda match: token,
                    summary,
                )
    placeholders = re.findall(r"\{\{([^{}]+)\}\}", summary)
    for key in placeholders:
        if key not in selected or key not in facts or facts[key]["value"] is None:
            raise CompositionValidationError("Answer uses an unsupported quantity placeholder")
    remainder = re.sub(r"\{\{[^{}]+\}\}", "", summary)
    if re.search(r"\d|[{}]", remainder):
        raise CompositionValidationError(
            "Answer must use validated quantity placeholders, not generated numbers"
        )
    for claim in re.finditer(
        r"\b(proves?|proven|confirms?|confirmed|confirming|definitively)\b", summary, re.IGNORECASE
    ):
        prefix = summary[max(0, claim.start() - 40) : claim.start()].lower()
        if not re.search(
            r"\b(not|no|without|cannot|can't|doesn't|don't|rather than)\b.{0,25}$", prefix
        ):
            raise CompositionValidationError(
                "Do not claim historical observations prove or confirm "
                "a physical constraint or cause; qualify the conclusion"
            )
    if set(placeholders) & {"simulation.baseline", "simulation.scenario", "simulation.gain"}:
        if "simulation.gain_interval" not in placeholders:
            raise CompositionValidationError(
                "Simulation output claims require their uncertainty interval"
            )
    for key in placeholders:
        summary = summary.replace("{{" + key + "}}", facts[key]["value"])
    return summary
