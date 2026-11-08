"""Transparent bounded calibration against the illustrative exercise target."""

from bottleneck_analyzer.simulation.config import Distribution, SimulationConfig, updated
from bottleneck_analyzer.simulation.scenarios import replications


def with_robot_repair(config: SimulationConfig, station_name: str, mean: float) -> SimulationConfig:
    stations = []
    for station in config.stations:
        failures = tuple(
            f.model_copy(
                update={
                    "repair": Distribution(
                        mean=mean, cv=f.repair.cv, minimum=min(f.repair.minimum, mean)
                    )
                }
            )
            if station.name == station_name and f.category.value == "robot_fault"
            else f
            for f in station.failures
        )
        stations.append(station.model_copy(update={"failures": failures}))
    return updated(config, stations=tuple(stations))


def calibrate(
    config: SimulationConfig,
    seeds: list[int],
    repair_means=(360, 480, 600, 720),
    target: float = 46,
    tolerance: float = 1,
    progress=None,
) -> dict:
    trials = []
    for value in repair_means:
        candidate = with_robot_repair(config, "Hemming", value)
        results = replications(candidate, seeds)
        actual = results["throughput"]["mean"]
        trials.append(
            {
                "changed_parameter": "Hemming robot mean repair seconds",
                "initial_value": config.stations[4].failures[0].repair.mean,
                "value": value,
                "results": results,
                "absolute_deviation": abs(actual - target),
                "percentage_deviation": 100 * abs(actual - target) / target,
            }
        )
        if progress:
            progress(value, actual)
    selected = min(trials, key=lambda trial: trial["absolute_deviation"])
    accepted = selected["absolute_deviation"] <= tolerance
    final = with_robot_repair(config, "Hemming", selected["value"])
    final = updated(
        final, calibration_status="calibration_passed" if accepted else "outside_tolerance"
    )
    return {
        "target_jph": target,
        "tolerance_jph": tolerance,
        "seeds": seeds,
        "selected_config": final.model_dump(mode="json"),
        "status": final.calibration_status,
        "trials": trials,
        "reason_for_search": (
            "Explore a declared 6–12 minute synthetic robot-repair range; other station, "
            "failure, buffer, release and mix assumptions remain fixed."
        ),
        "limitations": (
            "Calibration to an illustrative synthetic target is not real-plant validation. "
            "Independent evaluation seeds are required."
        ),
    }
