"""Terminal entry point for Stage 6; business HTTP endpoints belong to Stage 7."""

import argparse
import json
from pathlib import Path

from bottleneck_analyzer.agents.contracts import InvestigationRequest
from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.core.logging import configure_logging
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.workflows.graph import InvestigationWorkflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path, help="Investigation request JSON")
    parser.add_argument("--report", type=Path, help="Fresh output path; refuses overwrite")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("Report path already exists")
    engine = None
    try:
        configure_logging(get_settings().log_level)
        if args.request.stat().st_size > 20000:
            raise ValueError("Request file exceeds 20 KB")
        request = InvestigationRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
        engine = create_db_engine()
        response = InvestigationWorkflow(engine).run(request)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as output:
                output.write(response.model_dump_json(indent=2))
        print(response.answer)
        for error in response.errors:
            print(f"{error.component} ({error.category}): {error.message}")
        if response.outcome == "incomplete":
            for warning in response.warnings:
                print(f"Warning: {warning}")
        print(json.dumps({"outcome": response.outcome, "audit_id": str(response.audit_id)}))
        return 0 if response.outcome == "completed" else 2
    except Exception as exc:
        print(f"Investigation failed ({type(exc).__name__}); check configuration and scope.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
