"""Read-only terminal evidence retrieval; enrichment is intentionally not automatic."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.retrieval.contracts import RetrievalRequest
from bottleneck_analyzer.retrieval.service import retrieve


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--station", action="append", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--incident", action="append", default=[])
    parser.add_argument("--work-order", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    engine = None
    try:
        request = RetrievalRequest(
            dataset=args.dataset,
            stations=args.station,
            start_time=args.start,
            end_time=args.end,
            incident_ids=args.incident,
            work_order_ids=args.work_order,
            query=args.query,
            limit=args.limit,
        )
        engine = create_db_engine()
        result = retrieve(engine, request)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as out:
                out.write(result.model_dump_json(indent=2))
        print(
            json.dumps(
                {
                    "dataset": result.dataset_name,
                    "returned": len(result.evidence),
                    "methods_run": result.diagnostics.methods_run,
                    "unavailable": result.diagnostics.unavailable,
                    "assessments": [a.label for a in result.assessments],
                    "report": str(args.report),
                }
            )
        )
        return 0
    except SQLAlchemyError as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": "Database retrieval failed"}))
        return 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
