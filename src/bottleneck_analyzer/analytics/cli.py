"""Explicit local analytics command; never executes simulation or modifies datasets."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.analytics.service import analyze
from bottleneck_analyzer.db.session import create_db_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--model", choices=["SUV", "Sedan"])
    parser.add_argument("--shift", choices=["shift_1", "shift_2"])
    parser.add_argument("--shift-id")
    parser.add_argument("--station")
    parser.add_argument("--utc-hour", type=int, action="append", default=[])
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--assessment", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    engine = None
    try:
        scope = AnalyticsScope(
            dataset=args.dataset,
            start_time=args.start,
            end_time=args.end,
            model=args.model,
            shift=args.shift,
            shift_id=args.shift_id,
            station=args.station,
            utc_hours=args.utc_hour,
        )
        engine = create_db_engine()
        result = analyze(
            engine, scope, comparison_path=args.comparison, assessment_path=args.assessment
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            # Refuse to replace an earlier report accidentally.
            with args.report.open("x", encoding="utf-8") as output:
                output.write(result.model_dump_json(indent=2))
        print(
            json.dumps(
                {
                    "dataset": result.dataset_name,
                    "completed": result.overall.line.completed,
                    "scheduled_hours": result.overall.line.scheduled_hours,
                    "jph": result.overall.line.jph,
                    "leading_candidate": result.overall.leading_candidate,
                    "segments": len(result.segments),
                    "report": str(args.report),
                }
            )
        )
        return 0
    except SQLAlchemyError as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": "Database analytics failed"}))
        return 1
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
