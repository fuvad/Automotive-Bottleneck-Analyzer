"""Explicit validation experiments for design rate, release sufficiency and Framing."""

import argparse
import json
from pathlib import Path

from bottleneck_analyzer.data.generators.cli import export_history
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.simulation.cli import write_report
from bottleneck_analyzer.simulation.config import Distribution, SimulationConfig, updated
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.persistence import persist_result, project_result
from bottleneck_analyzer.simulation.scenarios import sensitivity
from bottleneck_analyzer.simulation.validation import validate_result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--fixture", type=Path, default=Path("tests/fixtures/simulation-framing.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("data/processed/stage3/reference-cases.json")
    )
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    base = SimulationConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    stations = tuple(
        station.model_copy(
            update={
                "processing": Distribution(
                    mean=fixture["processing_mean_seconds"],
                    cv=station.processing.cv,
                    minimum=station.processing.minimum,
                )
            }
        )
        if station.name == fixture["station"]
        else station
        for station in base.stations
    )
    framing = updated(
        base,
        name="sim-framing-validation-v1",
        days=fixture["days"],
        seed=fixture["sensitivity_seeds"][0],
        stations=stations,
        record_history=True,
        calibration_status="stress_case_not_calibrated",
    )
    measured = sensitivity(framing, fixture["sensitivity_seeds"])
    if measured["primary"] != fixture["expected_primary"]:
        raise ValueError("Measured constraint does not match the declared stress-case expectation")
    result = run_simulation(framing)
    validate_result(result)
    largest_fault = max(result.metrics["stations"], key=lambda s: s["fault_seconds"])["station"]
    print(
        f"Framing case measured primary={measured['primary']}; most downtime={largest_fault}",
        flush=True,
    )
    ideal_stations = tuple(
        station.model_copy(
            update={
                "processing": Distribution(mean=60, cv=0, minimum=1),
                "failures": (),
                "suv_multiplier": 1,
                "sedan_multiplier": 1,
            }
        )
        for station in base.stations
    )
    ideal = run_simulation(
        updated(
            base,
            days=1,
            stations=ideal_stations,
            record_history=False,
            calibration_status="design_reference_check",
        )
    )
    if not 59 <= ideal.metrics["jph"] <= 60.1:
        raise ValueError("The idealized line is inconsistent with the 60-JPH design reference")
    normal = run_simulation(updated(base, days=3, record_history=False))
    saturated = run_simulation(updated(base, days=3, release_rate_jph=90, record_history=False))
    release_change = saturated.metrics["jph"] - normal.metrics["jph"]
    if abs(release_change) > 0.5:
        raise ValueError("Baseline release cadence may be constraining line output")
    report = {
        "framing_config": framing.model_dump(mode="json"),
        "framing_metrics": result.metrics,
        "framing_sensitivity": measured,
        "largest_raw_downtime_station": largest_fault,
        "idealized_design_case": ideal.metrics,
        "release_sufficiency": {
            "days": 3,
            "seed": base.seed,
            "baseline_rate": base.release_rate_jph,
            "test_rate": 90,
            "baseline_jph": normal.metrics["jph"],
            "test_jph": saturated.metrics["jph"],
            "gain_jph": release_change,
        },
        "persistence": "not_requested",
    }
    if args.persist:
        history = project_result(result)
        report["manifest"] = str(export_history(history, Path("data/raw") / framing.name))
        engine = create_db_engine()
        try:
            with engine.begin() as connection:
                report["persistence"] = persist_result(connection, result)
        finally:
            engine.dispose()
    write_report(args.report, report)
    print(
        json.dumps(
            {
                "framing_primary": measured["primary"],
                "most_downtime": largest_fault,
                "idealized_jph": ideal.metrics["jph"],
                "release_check": report["release_sufficiency"],
                "persistence": report["persistence"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
