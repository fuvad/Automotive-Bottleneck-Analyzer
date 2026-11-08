"""Deterministic provenance merge and conservative evidence assessment."""

import re
from collections import defaultdict

from bottleneck_analyzer.retrieval.contracts import (
    CandidateContext,
    Evidence,
    EvidenceAssessment,
)


def content_warnings(item: Evidence) -> list[str]:
    warnings = []
    if re.search(
        r"\bno (?:robot |equipment )?(?:fault|alarm|failure|issue)\b|"
        r"\bnot (?:confirmed|observed)\b",
        item.text,
        re.I,
    ):
        warnings.append("Explicit denial or conflicting account: retain for human review")
    if re.search(
        r"ignore.{0,40}(instructions|previous)|system prompt|execute.{0,20}(sql|command)|"
        r"drop table|api.key|you are (an|a) (ai|assistant)",
        item.text + " " + (item.recorded_cause or ""),
        re.I | re.S,
    ):
        warnings.append(
            "Instruction-like source content: retained as untrusted data, excluded from assessment"
        )
    if item.historian_quality in {"bad", "missing"} or (
        item.source_type == "historian_observation" and item.historian_value is None
    ):
        warnings.append("Invalid or missing historian quality/value: not a valid measurement")
    if item.source_system == "SOP":
        warnings.append("Procedure reference, not evidence that an action or incident occurred")
    return warnings


def merge_results(items: list[Evidence], limit: int) -> tuple[list[Evidence], int]:
    """Identity-based merging never conflates distinct incidents, versions or spans."""
    merged: dict[str, Evidence] = {}
    for item in items:
        existing = merged.get(item.evidence_id)
        if existing is None:
            merged[item.evidence_id] = item.model_copy(deep=True)
        else:
            existing.retrieval_methods = sorted(
                set(existing.retrieval_methods + item.retrieval_methods)
            )
            existing.scores.update(item.scores)
            for link in item.links:
                if link not in existing.links:
                    existing.links.append(link)
            # A direct relation to the target may coexist with other inferred
            # edges; preserve every edge and never rewrite its original label.
            if item.relationship == "direct":
                existing.relationship = item.relationship
                existing.relationship_basis = item.relationship_basis

    def key(item: Evidence) -> tuple:
        methods = item.retrieval_methods
        return (
            0
            if "exact" in methods and item.relationship == "direct"
            else 1
            if "exact" in methods
            else 2,
            -sum(1 / (60 + item.scores[m]) for m in item.retrieval_methods),
            item.recorded_at,
            item.evidence_id,
        )

    ranked = sorted(merged.values(), key=key)
    return ranked[:limit], len(merged)


def assess(
    stations: list[str], evidence: list[Evidence], contexts: list[CandidateContext]
) -> list[EvidenceAssessment]:
    result = []
    for station in stations:
        context = next((c for c in contexts if c.station == station), None)
        items = [e for e in evidence if e.station == station]
        excluded = [
            e
            for e in items
            if any(
                "excluded from assessment" in w
                or "not a valid measurement" in w
                or "conflicting account" in w
                for w in e.warnings
            )
        ]
        usable = [
            e for e in items if e not in excluded and e.source_system != "SOP" and e.text.strip()
        ]
        warnings = ["No causal or recoverable-output claim is established by retrieved text"]
        if context:
            warnings.extend(context.conflicting_indicators)
            if context.model:
                warnings.append("Evidence has no exclusive vehicle-model attribution")
        if excluded:
            warnings.append(
                "Some retrieved records were excluded from interpretation due to content or quality"
            )
        causes = [
            e for e in usable if e.recorded_cause and e.source_type == "maintenance_work_order"
        ]
        if causes:
            label = "recorded_maintenance_cause"
            statement = (
                "Maintenance explicitly recorded (not line-level causal proof): "
                + "; ".join(dict.fromkeys(e.recorded_cause for e in causes))
            )
            support = causes
        else:
            incidents = defaultdict(list)
            for e in usable:
                if e.incident_id and e.relationship == "direct":
                    incidents[e.incident_id].append(e)
            coherent = [
                group
                for group in incidents.values()
                if len({e.source_system for e in group}) >= 2
                and any(e.source_type == "fault_event" for e in group)
                and any(e.source_type == "maintenance_work_order" for e in group)
            ]
            if coherent and context and (context.indicators.get("fault_fraction") or 0) > 0:
                label = "supported_hypothesis"
                support = [e for group in coherent for e in group]
                statement = (
                    "Linked fault and maintenance records support equipment interruptions as a "
                    "possible contributor to observed station fault occupancy. "
                    "They do not establish a component cause or line-level output loss."
                )
            elif usable:
                label = "observed_association"
                support = usable
                statement = (
                    "Records are associated with the selected station/period or incident. "
                    "No causal explanation or station-attributable output loss is established."
                )
            else:
                label = "insufficient_evidence"
                support = []
                statement = (
                    "Available records are absent, procedural only, invalid or inadequate "
                    "for a cause assessment."
                )
        result.append(
            EvidenceAssessment(
                station=station,
                label=label,
                statement=statement,
                evidence_ids=sorted({e.evidence_id for e in support}),
                conflicting_evidence_ids=sorted(e.evidence_id for e in excluded),
                candidate_context=context,
                warnings=warnings,
            )
        )
    return result
