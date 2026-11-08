"""Run, calibrate, compare, export and persist controlled SimPy experiments."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from bottleneck_analyzer.data.generators.cli import export_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.domain.enums import InterventionMethod
from bottleneck_analyzer.simulation.calibration import calibrate
from bottleneck_analyzer.simulation.config import Intervention, SimulationConfig, updated
from bottleneck_analyzer.simulation.engine import run_simulation
from bottleneck_analyzer.simulation.persistence import (
    project_result,
    topology_from_dataset,
    validate_simulation_history,
)
from bottleneck_analyzer.simulation.scenarios import (
    assess_comparison,
    compare,
    replications,
    sensitivity,
)
from bottleneck_analyzer.simulation.validation import validate_result


def write_report(path: Path, payload: dict) -> None:
    """Create immutable experiment reports, accepting an identical replay."""
    content = json.dumps(payload, indent=2, sort_keys=True)
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        candidate = json.loads(content)
        # Keep the original report immutable while accepting a verified dataset replay.
        for report in (previous, candidate):
            if isinstance(report.get("persistence"), dict):
                report["persistence"].pop("created", None)
        if previous != candidate:
            raise ValueError(f"Report already exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("baseline", "scenario", "replicate", "calibrate", "sensitivity", "assess"),
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--days", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--replications", type=int, default=20)
    parser.add_argument("--seed-start", type=int, default=1001)
    parser.add_argument("--target", default="Hemming")
    parser.add_argument(
        "--method", choices=[m.value for m in InterventionMethod], default="repair_duration"
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--from-dataset", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--save-config", type=Path)
    parser.add_argument("--comparison", type=Path)
    args = parser.parse_args()
    persistence_failed = False
    if args.replications < 1:
        parser.error("replications must be positive")
    config = (
        SimulationConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.config
        else SimulationConfig()
    )
    changes = {
        k: v
        for k, v in {"name": args.name, "days": args.days, "seed": args.seed}.items()
        if v is not None
    }
    config = updated(config, **changes)
    if args.from_dataset:
        engine = create_db_engine()
        try:
            with engine.connect() as connection:
                config = topology_from_dataset(connection, config)
        finally:
            engine.dispose()
    seeds = list(range(args.seed_start, args.seed_start + args.replications))

    def progress(key, value):
        print(f"completed {key}: {value:.6f}", flush=True)

    if args.command == "assess":
        if args.comparison is None:
            parser.error("--comparison must point to a completed paired experiment report")
        report = assess_comparison(
            json.loads(args.comparison.read_text(encoding="utf-8")), seeds, config.days
        )
    elif args.command == "calibrate":
        report = calibrate(config, seeds, progress=progress)
    elif args.command == "replicate":
        report = replications(config, seeds, progress=progress)
    elif args.command == "scenario":
        intervention = Intervention(station=args.target, method=args.method)
        report = compare(config, intervention, seeds, progress=progress)
    elif args.command == "sensitivity":
        report = sensitivity(config, seeds)
    else:
        result = run_simulation(updated(config, record_history=True))
        report = {
            "dataset": config.name,
            "config": result.config.model_dump(mode="json"),
            "validation": validate_result(result),
            "metrics": result.metrics,
            "persistence": "not_requested",
        }
        if args.export or args.persist:
            history = project_result(result)
            report["history_validation"] = validate_simulation_history(history)
            if args.export:
                report["manifest"] = str(export_history(history, Path("data/raw") / config.name))
            if args.persist:
                engine = create_db_engine()
                try:
                    from sqlalchemy import select

                    from bottleneck_analyzer.db.models.production import Dataset, SOPDocument

                    with engine.begin() as connection:
                        count = connection.execute(
                            select(SOPDocument.id)
                            .join(Dataset, Dataset.id == SOPDocument.dataset_id)
                            .where(Dataset.name == config.sop_reference_dataset)
                        ).all()
                        if not count:
                            raise ValueError("Referenced SOP dataset is unavailable")
                        report["persistence"] = load_history(
                            connection, history, validator=validate_simulation_history
                        )
                except SQLAlchemyError as exc:
                    persistence_failed = True
                    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                    report["persistence"] = {
                        "status": "failed",
                        "commit_confirmed": False,
                        "sqlstate": sqlstate,
                        "error_type": type(getattr(exc, "orig", exc)).__name__,
                        "detail": (
                            "PostgreSQL storage is full. Free disk space before retrying."
                            if sqlstate == "53100"
                            else (
                                "Database operation failed; commit is not confirmed. "
                                "Check database availability."
                            )
                        ),
                    }
                finally:
                    engine.dispose()
    if args.report:
        write_report(args.report, report)
    if args.save_config:
        if args.command != "calibrate":
            parser.error("--save-config is only supported for calibration")
        write_report(args.save_config, report["selected_config"])
    # Full per-run details are saved in the report; keep terminal output readable.
    summary = {
        k: v
        for k, v in report.items()
        if k
        not in {
            "runs",
            "trials",
            "config",
            "baseline_config",
            "scenario_config",
            "selected_config",
            "metrics",
        }
    }
    summary.update(
        dataset=config.name,
        days=config.days,
        seed=config.seed,
        release_rate_jph=config.release_rate_jph,
        suv_fraction=config.suv_fraction,
        report=str(args.report) if args.report else None,
    )
    if "metrics" in report:
        m = report["metrics"]
        summary["metrics"] = {
            k: m[k]
            for k in (
                "completed",
                "released",
                "final_wip",
                "jph",
                "scheduled_hours",
                "average_wip",
                "maximum_wip",
                "stations",
                "constraints",
            )
        }
    if args.command == "calibrate":
        summary["selected_robot_repair_mean_seconds"] = report["selected_config"]["stations"][4][
            "failures"
        ][0]["repair"]["mean"]
    print(json.dumps(summary, indent=2))
    return 1 if persistence_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
