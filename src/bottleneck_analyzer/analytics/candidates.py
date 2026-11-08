"""Transparent observational ranking; scores are not constraint probabilities."""

from bottleneck_analyzer.analytics.contracts import Candidate, StationMetrics


def ratio(value: float | None, denominator: float) -> float | None:
    return value / denominator if value is not None and denominator > 0 else None


def rank_candidates(stations: list[StationMetrics], model_segment: bool = False) -> list[Candidate]:
    results = []
    by_sequence = {s.sequence: s for s in stations}
    max_service = max((s.mean_service_seconds or 0 for s in stations), default=0)
    for s in stations:
        up, down = by_sequence.get(s.sequence - 1), by_sequence.get(s.sequence + 1)
        service = ratio(s.mean_service_seconds, max_service)
        queue = ratio(s.average_input_queue, s.input_capacity or 0)
        if model_segment:
            busy = service
            upstream = ratio(up.mean_blocked_wall_seconds, 3600) if up else None
            downstream = ratio(down.mean_waiting_wall_seconds, 3600) if down else None
            own_block = own_starve = None
        else:
            busy = ratio(
                (s.processing_seconds or 0) + (s.faulted_seconds or 0), s.scheduled_seconds
            )
            upstream = ratio(up.blocked_seconds, up.scheduled_seconds) if up else None
            downstream = ratio(down.starved_seconds, down.scheduled_seconds) if down else None
            own_block = ratio(s.blocked_seconds, s.scheduled_seconds)
            own_starve = ratio(s.starved_seconds, s.scheduled_seconds)
        indicators = {
            "busy_pressure": busy,
            "queue_fraction": queue,
            "upstream_blocking": upstream,
            "downstream_starvation": downstream,
            "relative_service_demand": service,
            "own_blocking": own_block,
            "own_starvation": own_starve,
            "utilization": s.utilization,
            "fault_fraction": ratio(s.faulted_seconds, s.scheduled_seconds),
        }
        # Missing indicators contribute zero, remain null, and weaken evidence classification.
        score = sum(
            weight * min(1, max(0, value or 0))
            for weight, value in (
                (0.30, busy),
                (0.25, queue),
                (0.20, upstream),
                (0.20, downstream),
                (0.05, service),
            )
        )
        score -= 0.10 * ((own_block or 0) + (own_starve or 0))
        supporting, conflicting = [], []
        for label, value, threshold in (
            (
                "High processing/fault occupancy"
                if not model_segment
                else "High relative service demand",
                busy,
                0.75,
            ),
            ("Input queue accumulation", queue, 0.5),
            ("Upstream blocking", upstream, 0.05),
            ("Downstream starvation", downstream, 0.05),
        ):
            if value is not None and value >= threshold:
                supporting.append(f"{label}: {value:.4f}")
        if own_block is not None and own_block > 0.1:
            conflicting.append("Substantial own blocking suggests downstream restriction")
        if own_starve is not None and own_starve > 0.1:
            conflicting.append("Substantial own starvation suggests upstream restriction")
        if queue is None:
            conflicting.append("Queue occupancy unavailable")
        if s.mean_service_seconds is None:
            conflicting.append("Active service samples unavailable")
        sufficient = s.operations >= 30 and s.scheduled_seconds >= 1800
        if not model_segment:
            sufficient = sufficient and (s.state_coverage or 0) >= 0.95
            sufficient = sufficient and (s.overlap_seconds or 0) <= 0.001
        strength = "insufficient_evidence"
        if sufficient:
            strength = (
                "strong"
                if len(supporting) >= 3 and not model_segment
                else "moderate"
                if len(supporting) >= 2
                else "weak"
            )
        if model_segment:
            conflicting.append(
                "Shared machine states cannot be attributed exclusively to this model"
            )
        results.append(
            Candidate(
                station=s.station,
                rank=1,
                score=score,
                indicators=indicators,
                supporting_evidence=supporting,
                contradicting_evidence=conflicting,
                strength=strength,
                operations=s.operations,
                state_coverage=s.state_coverage,
                explanation="Observational ranking from measured demand and flow propagation; "
                "not proof of a line constraint or a probability.",
                aggregate_ids=[r.aggregate_id for r in s.references],
            )
        )
    results.sort(key=lambda c: (-c.score, c.station))
    for i, c in enumerate(results):
        c.rank = i + 1
    return results


def leader(candidates: list[Candidate]) -> str | None:
    if not candidates or candidates[0].strength not in {"strong", "moderate"}:
        return None
    if len(candidates) > 1 and candidates[0].score - candidates[1].score < 0.01:
        return None
    return candidates[0].station
