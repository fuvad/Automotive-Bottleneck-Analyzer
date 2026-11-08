"""Historical analysis over one coherent, read-only PostgreSQL snapshot."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine

from bottleneck_analyzer.analytics.calendar import Segment, build_segments, seconds
from bottleneck_analyzer.analytics.candidates import leader, rank_candidates, ratio
from bottleneck_analyzer.analytics.contracts import (
    AggregateReference,
    AnalyticsResult,
    AnalyticsScope,
    LineMetrics,
    SegmentResult,
    StationMetrics,
)
from bottleneck_analyzer.analytics.repository import AnalyticsRepository
from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.db.models.production import SourceRecord
from bottleneck_analyzer.domain.models import EvidenceReference


def analyze(
    engine: Engine,
    scope: AnalyticsScope,
    *,
    design_rate: float | None = None,
    comparison_path: Path | None = None,
    assessment_path: Path | None = None,
) -> AnalyticsResult:
    """Own a repeatable-read transaction that PostgreSQL enforces as read-only."""
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            return analyze_connection(
                connection,
                scope,
                design_rate=design_rate,
                comparison_path=comparison_path,
                assessment_path=assessment_path,
            )


def analyze_connection(
    connection: Connection,
    scope: AnalyticsScope,
    *,
    design_rate: float | None = None,
    comparison_path: Path | None = None,
    assessment_path: Path | None = None,
) -> AnalyticsResult:
    """SELECT-only core; caller owns its transaction (also used by isolated tests)."""
    # PostgreSQL overestimates lateral generate_series cardinality. JIT compilation
    # of these bounded calendar joins otherwise costs more than the calculations.
    connection.execute(text("SET LOCAL jit = off"))
    # date_trunc(timestamptz) follows the session zone. Pin only this transaction
    # to UTC so hour equality joins agree with the UTC calendar window splits.
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    repo = AnalyticsRepository(connection, scope.dataset)
    segments = build_segments(repo.dataset, repo.shifts, repo.exclusions, scope)
    repo.configure(segments)
    ops = {(r["key"], r["station_id"]): r for r in repo.operations()}
    states = defaultdict(dict)
    for r in repo.states():
        states[(r["key"], r["station_id"])][r["state"]] = r
    lines = defaultdict(list)
    for r in repo.line():
        lines[r["key"]].append(r)
    simulation = repo.dataset["provenance"] == "simulation"
    queue = {(r["key"], r["station"]): r for r in repo.occupancy("queue")} if simulation else {}
    wip = {r["key"]: r for r in repo.occupancy("wip")}
    sample_ids = {r["source_record_id"] for r in ops.values()}
    sample_ids.update(r["sample"] for group in states.values() for r in group.values())
    sources = (
        {
            str(r.id): r
            for r in connection.execute(
                select(SourceRecord.id, SourceRecord.source_id, SourceRecord.system).where(
                    SourceRecord.dataset_id == repo.dataset_id,
                    SourceRecord.id.in_(sorted(sample_ids)),
                )
            )
        }
        if sample_ids
        else {}
    )
    signature = hashlib.sha256(scope.model_dump_json().encode()).hexdigest()[:16]
    rate = design_rate if design_rate is not None else get_settings().design_production_rate_jph
    if rate < 0:
        raise ValueError("design_rate cannot be negative")

    def reference(
        segment: Segment, station: dict, measurement: str, count: int, sample: str | None
    ) -> AggregateReference:
        source = sources.get(sample)
        return AggregateReference(
            aggregate_id=f"{repo.dataset_id}/{signature}/{segment.key}/{station['sequence']}/{measurement}",
            dataset_id=repo.dataset_id,
            segment_key=segment.key,
            station_id=station["id"],
            measurement=measurement,
            record_count=count,
            samples=[
                EvidenceReference(
                    evidence_id=str(source.id),
                    source_type=source.system,
                    source_id=source.source_id,
                    relationship="direct",
                )
            ]
            if source
            else [],
        )

    results = []
    for segment in segments:
        scheduled = seconds(segment.scheduled)
        wall = seconds(segment.windows)
        model_segment = segment.model is not None
        counts = {"SUV": 0, "Sedan": 0}
        admitted = completed = flow = 0
        stocks = {"initial_wip": 0, "final_wip": 0}
        for row in lines[segment.key]:
            admitted += row["admitted"]
            completed += row["completed"]
            flow += float(row["flow"] or 0)
            if row["model"] in counts:
                counts[row["model"]] = row["completed"]
            stocks = row
        occupancy = wip.get(segment.key, {})
        hours = scheduled / 3600
        jph = ratio(completed, hours)
        metrics = LineMetrics(
            admitted=admitted,
            completed=completed,
            initial_wip=stocks["initial_wip"],
            final_wip=stocks["final_wip"],
            scheduled_hours=hours,
            jph=jph,
            design_rate_jph=rate,
            design_gap_jph=rate - jph if jph is not None and not model_segment else None,
            design_gap_bodies=rate * hours - completed if hours and not model_segment else None,
            completion_counts_by_model=counts,
            average_flow_seconds=ratio(flow, completed),
            average_wip=ratio(occupancy.get("area"), scheduled),
            maximum_wip=occupancy.get("maximum"),
        )
        station_results = []
        for station in repo.stations:
            key = segment.key, station["id"]
            op, state = ops.get(key, {}), states[key]
            covered = max((r["covered"] for r in state.values()), default=0)
            overlap = max((r["overlap"] for r in state.values()), default=0)
            valid_states = not model_segment and overlap <= 0.001
            coverage = ratio(covered, scheduled) if not model_segment else None
            warnings = []
            if not model_segment and scheduled and covered < scheduled - 0.001:
                warnings.append(
                    "Incomplete scheduled state coverage; missing intervals are not imputed"
                )
            if overlap > 0.001:
                warnings.append(
                    "Overlapping states: exclusive state totals suppressed to avoid double-counting"
                )
            if model_segment:
                warnings.append(
                    "Shared station states unavailable by model; service/waits use completed visits"
                )
            if not simulation:
                warnings.append(
                    "Queue traces and active service work unavailable in authored fixture"
                )
            q = queue.get((segment.key, station["sequence"]), {})
            input_capacity = next(
                (
                    b["capacity"]
                    for b in repo.buffers
                    if b["downstream_station_id"] == station["id"]
                ),
                None,
            )
            if station["sequence"] == 1 and simulation:
                input_capacity = repo.dataset["config"].get("input_capacity")
            refs = [
                reference(
                    segment,
                    station,
                    "completed_operations",
                    op.get("operations", 0),
                    op.get("source_record_id"),
                )
            ]
            for name, record in sorted(state.items()):
                refs.append(
                    reference(segment, station, f"state:{name}", record["count"], record["sample"])
                )

            def duration(name: str) -> float | None:
                return float(state.get(name, {}).get("seconds", 0)) if valid_states else None

            service = op.get("service")
            capacity = ratio(3600, service or 0)
            fault_fraction = ratio(duration("faulted"), scheduled)
            station_results.append(
                StationMetrics(
                    station_id=station["id"],
                    station=station["name"],
                    sequence=station["sequence"],
                    operations=op.get("operations", 0),
                    scheduled_seconds=scheduled,
                    processing_seconds=duration("running"),
                    utilization=ratio(duration("running"), scheduled),
                    faulted_seconds=duration("faulted"),
                    blocked_seconds=duration("blocked"),
                    starved_seconds=duration("starved"),
                    planned_closure_seconds=wall - scheduled if not model_segment else None,
                    state_count=sum(r["count"] for r in state.values()),
                    state_coverage=coverage,
                    overlap_seconds=overlap if not model_segment else None,
                    service_sample_count=op.get("service_count", 0),
                    mean_service_seconds=service,
                    processing_capacity_jph=capacity,
                    effective_capacity_jph=capacity * (1 - fault_fraction)
                    if capacity is not None and fault_fraction is not None
                    else None,
                    mean_operation_elapsed_seconds=op.get("elapsed"),
                    mean_waiting_wall_seconds=op.get("waiting"),
                    mean_blocked_wall_seconds=op.get("blocking"),
                    average_input_queue=ratio(q.get("area", 0), scheduled) if simulation else None,
                    maximum_input_queue=q.get("maximum", 0) if simulation and scheduled else None,
                    input_capacity=input_capacity,
                    queue_basis="Arrival-to-start occupancy; scheduled-time weighting; "
                    "includes retained censored visits"
                    if simulation
                    else "Unavailable",
                    references=refs,
                    warnings=warnings,
                )
            )
        ranked = rank_candidates(station_results, model_segment)
        leading = leader(ranked)
        warnings = []
        if not scheduled:
            warnings.append("No scheduled production: JPH is unavailable")
        if model_segment:
            warnings.append(
                "Model JPH is a contribution to mixed-line output, not exclusive-model capacity"
            )
            if completed < 30:
                warnings.append("Small model sample: fewer than 30 completions")
        if len(segment.windows) > 1:
            warnings.append(
                "WIP stocks use first/last boundaries; admissions/completions use selected windows"
            )
        if leading is None:
            warnings.append("Insufficient or conflicting indicators: no leading candidate asserted")
        # Rank with all seven stations so a station filter cannot erase adjacent evidence.
        if scope.station:
            station_results = [s for s in station_results if s.station == scope.station]
            ranked = [c for c in ranked if c.station == scope.station]
            if leading != scope.station:
                leading = None
        results.append(
            SegmentResult(
                key=segment.key,
                kind=segment.kind,
                label=segment.label,
                start_time=min((a for a, _ in segment.windows), default=repo.dataset["start_time"]),
                end_time=max((b for _, b in segment.windows), default=repo.dataset["end_time"]),
                shift_id=segment.shift_id,
                model=segment.model,
                utc_hour=segment.utc_hour,
                line=metrics,
                stations=station_results,
                candidates=ranked,
                leading_candidate=leading,
                warnings=warnings,
            )
        )
    overall, others = results[0], results[1:]
    shifts = [s for s in others if s.kind == "shift" and s.leading_candidate]
    for c in overall.candidates:
        c.dated_shifts_evaluated = sum(s.kind == "shift" for s in others)
        c.dated_shifts_resolved = len(shifts)
        c.dated_shift_leader_fraction = ratio(
            sum(s.leading_candidate == c.station for s in shifts), len(shifts)
        )
    changes = [
        f"{s.key}: {overall.leading_candidate or 'unresolved'} -> {s.leading_candidate}"
        for s in others
        if s.leading_candidate and s.leading_candidate != overall.leading_candidate
    ]
    warnings = ["Synthetic history: observational candidates are not proven real-plant constraints"]
    warnings.extend(sorted({w for s in results for m in s.stations for w in m.warnings}))
    if scope.station:
        warnings.append(
            "Station filter limits displayed stations; line throughput uses Final Inspection"
        )
    if len(repo.runs) > 1:
        raise ValueError("Multiple simulation runs in one dataset: ambiguous censored history")
    if simulation and not repo.runs:
        raise ValueError("Simulation dataset is missing its run metadata")
    evidence = []
    if repo.runs:
        r = repo.runs[0]
        evidence.append(
            {
                "type": "persisted_simulation_reference",
                "run_id": str(r["id"]),
                "configuration_id": str(r["configuration_id"]),
                "seed": r["seed"],
                "reference_jph": r["results"]["metrics"]["jph"],
                "qualification": "Full-run reference, not a filtered historical measurement",
            }
        )
    if comparison_path or assessment_path:
        evidence.append(load_assessment(repo.dataset, comparison_path, assessment_path))
    return AnalyticsResult(
        dataset_id=repo.dataset_id,
        dataset_name=repo.dataset["name"],
        provenance=repo.dataset["provenance"],
        content_hash=repo.dataset["content_hash"],
        scope=scope,
        overall=overall,
        segments=others,
        candidate_changes=changes,
        simulation_evidence=evidence,
        warnings=warnings,
        assumptions=[
            "Periods are timezone-aware [start,end); UTC-hour buckets pool dated hours",
            "JPH = Final Inspection completions / scheduled hours, including unplanned downtime",
            "Design gap is not station-attributable recoverable loss; a counterfactual is required",
            "Planned closure = selected wall time minus scheduled time, including off-shift",
            "Physical repair durations are never added to exclusive fault-state durations",
            "Model service/wait/block means use completed visits, including cross-boundary visits",
            "Queue maxima use positive-duration occupancy; simultaneous transitions are merged",
            "Time-average WIP includes machine-held bodies; maxima use scheduled time",
            "Scores organize historical signals; separate sensitivity tests modeled constraints",
            "No retrieval, root-cause agent, simulation execution, API or UI is performed",
        ],
    )


def load_assessment(
    dataset: dict, comparison_path: Path | None, assessment_path: Path | None
) -> dict:
    if comparison_path is None or assessment_path is None:
        raise ValueError(
            "Provide both comparison and assessment reports to verify their association"
        )
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    ignored = {"name", "seed", "record_history"}

    def normalized(config: dict) -> dict:
        return {k: v for k, v in config.items() if k not in ignored}

    if normalized(comparison["baseline_config"]) != normalized(dataset["config"]):
        raise ValueError("Simulation comparison configuration does not match the selected dataset")
    if comparison["baseline"] != assessment["baseline"]:
        raise ValueError("Assessment does not reference the supplied comparison summary")
    return {
        "type": "separate_simulation_sensitivity",
        "dataset_id": str(dataset["id"]),
        "comparison_sha256": hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
        "assessment_sha256": hashlib.sha256(assessment_path.read_bytes()).hexdigest(),
        "comparison_path": str(comparison_path),
        "assessment_path": str(assessment_path),
        "baseline_constraint": assessment["baseline_constraint"],
        "qualification": "Matching model configuration; sensitivity uses its own horizon/seeds. "
        "Separate modeling evidence, not part of the observational score or plant proof.",
    }
