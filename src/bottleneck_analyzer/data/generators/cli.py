"""Explicit command-line generation; never called during application startup."""

import argparse
import csv
import json
from pathlib import Path

from bottleneck_analyzer.data.connectors.mock import SOURCE_SYSTEMS
from bottleneck_analyzer.data.generators.history import EventHistory, generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.data.validation import validate_history
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.domain.manufacturing import DatasetConfig


def export_history(history: EventHistory, directory: Path) -> Path:
    """Write originals and SOP text to a dataset-specific directory without overwrite."""
    manifest = directory / "manifest.json"
    fingerprint = history.fingerprint()
    if directory.exists():
        if (
            manifest.exists()
            and json.loads(manifest.read_text(encoding="utf-8"))["fingerprint"] == fingerprint
        ):
            return manifest
        raise ValueError("Export directory exists with different or incomplete content")
    directory.mkdir(parents=True)
    for system in SOURCE_SYSTEMS:
        rows = [row for row in history.rows["source_record"] if row["system"] == system]
        suffix = ".csv" if system in {"MES", "historian"} else ".jsonl"
        path = directory / f"{system}{suffix}"
        with path.open("w", encoding="utf-8", newline="") as handle:
            if suffix == ".csv":
                fields = ["id", "source_id", "recorded_at", "station_id", "raw"]
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            **{key: row[key] for key in fields},
                            "raw": json.dumps(row["raw"], sort_keys=True),
                        }
                    )
            else:
                for row in rows:
                    handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
    for row in history.rows["sop_document"]:
        (directory / f"SOP-{row['id']}.txt").write_text(row["content"], encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "config": history.config.model_dump(mode="json"),
                "fingerprint": fingerprint,
                "counts": history.counts(),
                "provenance": "authored_fixture",
                "limitation": (
                    "Simulation-derived history will replace these authored fixtures in Stage 3."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="stage2-30day-v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", default="2026-09-01T00:00:00Z")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--vehicles-per-shift", type=int, default=345)
    parser.add_argument("--fault-focus", default=None)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    config = DatasetConfig(
        name=args.name,
        seed=args.seed,
        start_time=args.start,
        days=args.days,
        vehicles_per_shift=args.vehicles_per_shift,
        fault_focus=args.fault_focus,
    )
    history = generate_history(config)
    report = validate_history(history)
    if not args.validate_only:
        manifest = export_history(history, Path("data/raw") / config.name)
        engine = create_db_engine()
        try:
            with engine.begin() as connection:
                report = load_history(connection, history)
        finally:
            engine.dispose()
        report["manifest"] = str(manifest)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
