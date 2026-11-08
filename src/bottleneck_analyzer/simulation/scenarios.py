"""Paired replications, uncertainty and station-capacity sensitivity experiments."""

from collections import Counter
from math import sqrt
from statistics import mean, stdev

from bottleneck_analyzer.simulation.calendars import Calendar
from bottleneck_analyzer.simulation.config import Intervention, SimulationConfig, updated
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.metrics import candidates


def validate_seeds(seeds: list[int]) -> None:
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seeds)
    ):
        raise ValueError("Replications require distinct non-negative integer seeds")


def statistics(values: list[float]) -> dict:
    if not values:
        raise ValueError("At least one replication is required")
    n = len(values)
    average = mean(values)
    sd = stdev(values) if n > 1 else 0.0
    # Two-sided Student-t critical values, 95%; asymptotic expansion for df > 30.
    table = (
        0,
        12.706,
        4.303,
        3.182,
        2.776,
        2.571,
        2.447,
        2.365,
        2.306,
        2.262,
        2.228,
        2.201,
        2.179,
        2.160,
        2.145,
        2.131,
        2.120,
        2.110,
        2.101,
        2.093,
        2.086,
        2.080,
        2.074,
        2.069,
        2.064,
        2.060,
        2.056,
        2.052,
        2.048,
        2.045,
        2.042,
    )
    df = n - 1
    if n > 1:
        critical = table[df] if df <= 30 else 1.959964 + 2.3723 / df + 2.8225 / df**2
        half = critical * sd / sqrt(n)
        ci = [average - half, average + half]
    else:
        ci = None
    return {
        "n": n,
        "mean": average,
        "stdev": sd,
        "min": min(values),
        "max": max(values),
        "ci95": ci,
        "interval_method": "Student-t mean interval across independent seeds",
    }


def replications(config: SimulationConfig, seeds: list[int], progress=None) -> dict:
    validate_seeds(seeds)
    metrics = []
    for seed in seeds:
        metrics.append(run_simulation(updated(config, seed=seed, record_history=False)).metrics)
        if progress:
            progress(seed, metrics[-1]["jph"])
    return {
        "seeds": seeds,
        "config": config.model_dump(mode="json"),
        "throughput": statistics([m["jph"] for m in metrics]),
        "runs": metrics,
        "observational_candidate_distribution": dict(
            Counter(m["constraints"]["observational_candidates"][0]["station"] for m in metrics)
        ),
    }


def compare(
    config: SimulationConfig, intervention: Intervention, seeds: list[int], progress=None
) -> dict:
    validate_seeds(seeds)
    if config.intervention is not None:
        raise ValueError("Baseline must not already contain an intervention")
    scenario = updated(config, intervention=intervention, record_history=False)
    baseline = updated(config, record_history=False)
    runs = []
    for seed in seeds:
        before = run_simulation(updated(baseline, seed=seed))
        after = run_simulation(updated(scenario, seed=seed))
        calendar = Calendar(baseline)
        target_index = next(
            i for i, s in enumerate(config.stations) if s.name == intervention.station
        )

        def downtime(result):
            return sum(
                calendar.scheduled_between(f.start, f.end)
                for f in result.faults
                if f.station == target_index
                and f.category == intervention.category.value
                and f.equipment_id == intervention.equipment_id
            )

        runs.append(
            {
                "seed": seed,
                "baseline": before.metrics,
                "scenario": after.metrics,
                "gain_jph": after.metrics["jph"] - before.metrics["jph"],
                "baseline_target_fault_seconds": downtime(before),
                "scenario_target_fault_seconds": downtime(after),
            }
        )
        if progress:
            progress(seed, runs[-1]["gain_jph"])
    base = statistics([r["baseline"]["jph"] for r in runs])
    new = statistics([r["scenario"]["jph"] for r in runs])
    old_downtime = mean(r["baseline_target_fault_seconds"] for r in runs)
    new_downtime = mean(r["scenario_target_fault_seconds"] for r in runs)
    gain = statistics([r["gain_jph"] for r in runs])
    return {
        "seeds": seeds,
        "baseline_config": baseline.model_dump(mode="json"),
        "scenario_config": scenario.model_dump(mode="json"),
        "baseline": base,
        "scenario": new,
        "paired_gain": gain,
        "throughput_improvement_percentage": 100 * gain["mean"] / base["mean"]
        if base["mean"]
        else None,
        "baseline_target_fault_seconds": old_downtime,
        "scenario_target_fault_seconds": new_downtime,
        "realized_downtime_reduction_percentage": 100 * (1 - new_downtime / old_downtime)
        if old_downtime
        else None,
        "random_stream_strategy": (
            "Same seed; processing keyed by station/vehicle, gaps/repairs by "
            "station/category/equipment occurrence. Operating-time exposure changes with flow."
        ),
        "runs": runs,
    }


def sensitivity(config: SimulationConfig, seeds: list[int], factor: float = 0.9) -> dict:
    validate_seeds(seeds)
    if not 0 < factor < 1:
        raise ValueError("Sensitivity factor must be between zero and one")
    baseline = [
        run_simulation(updated(config, seed=seed, record_history=False)).metrics for seed in seeds
    ]
    gains = {}
    for index, station in enumerate(config.stations):
        stations = list(config.stations)
        distribution = station.processing.model_copy(
            update={
                "mean": station.processing.mean * factor,
                "minimum": station.processing.minimum * factor,
            }
        )
        stations[index] = station.model_copy(update={"processing": distribution})
        changed = updated(config, stations=tuple(stations), record_history=False)
        gains[station.name] = statistics(
            [
                run_simulation(updated(changed, seed=seed)).metrics["jph"] - before["jph"]
                for seed, before in zip(seeds, baseline, strict=True)
            ]
        )
    return {
        "days": config.days,
        "seeds": seeds,
        "processing_multiplier": factor,
        **candidates(baseline[0], gains),
    }


def assess_comparison(comparison: dict, seeds: list[int], days: int = 3) -> dict:
    """Re-evaluate both constraints using separate paired capacity perturbations."""
    before = SimulationConfig.model_validate(comparison["baseline_config"])
    after = SimulationConfig.model_validate(comparison["scenario_config"])
    if before.intervention is not None or after.intervention is None:
        raise ValueError("Expected a baseline and a separately targeted scenario")
    baseline = sensitivity(updated(before, days=days), seeds)
    scenario = sensitivity(updated(after, days=days), seeds)
    moved = (
        baseline["primary"] != scenario["primary"]
        if baseline["primary"] and scenario["primary"]
        else None
    )
    return {
        "baseline": comparison["baseline"],
        "scenario": comparison["scenario"],
        "paired_gain": comparison["paired_gain"],
        "realized_downtime_reduction_percentage": comparison[
            "realized_downtime_reduction_percentage"
        ],
        "throughput_improvement_percentage": comparison["throughput_improvement_percentage"],
        "baseline_constraint": baseline,
        "scenario_constraint": scenario,
        "constraint_moved": moved,
        "qualification": (
            "Constraint evidence uses the separately declared sensitivity horizon/seeds; "
            "comparison uncertainty uses the full paired runs."
        ),
    }
