"""Explicit live LLM acceptance; not imported by the ordinary regression suite."""

import argparse
import json
from pathlib import Path
from time import monotonic
from uuid import UUID

from sqlalchemy import select

from bottleneck_analyzer.agents.contracts import InvestigationRequest, KnowledgeInput, WorkflowState
from bottleneck_analyzer.agents.knowledge import KnowledgeAgent
from bottleneck_analyzer.agents.planner import (
    ClarificationRequired,
    PlannerAgent,
    UnsupportedQuestion,
)
from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.core.llm import OpenAIStructuredLLM
from bottleneck_analyzer.core.logging import configure_logging
from bottleneck_analyzer.db.models.production import InvestigationAudit
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.workflows.audit import load_context
from bottleneck_analyzer.workflows.graph import InvestigationWorkflow
from bottleneck_analyzer.workflows.validation import validate_plan


def planning(engine) -> dict:
    planner = PlannerAgent(OpenAIStructuredLLM(get_settings()))
    cases = [
        (
            "Which station is the strongest historical bottleneck candidate "
            "and what is the output gap?",
            "constraint_output_loss",
        ),
        ("What maintenance evidence may explain interruptions at Hemming?", "causes"),
        (
            "Does the historical bottleneck candidate differ by shift, "
            "SUV versus Sedan, or UTC hour?",
            "segmentation",
        ),
        ("What would a 30% reduction in robot repair duration at Hemming change?", "what_if"),
        ("What would a 30% reduction in robot failure rate at Hemming change?", "what_if"),
        (
            "Which station limits JPH, what evidence may explain its interruptions, and what would "
            "a 30% reduction in robot repair duration change?",
            "combined",
        ),
        ("What if robot-fault downtime is reduced by 30%?", "clarification_required"),
        ("Create a CMMS work order and execute changes on the PLC", "unsupported"),
    ]
    results = []
    for question, expected in cases:
        request = InvestigationRequest(
            question=question, scope={"dataset": "sim-30day-baseline-v1"}
        )
        context = load_context(engine, request.scope)
        scope = type(request.scope).model_validate(
            {
                **request.scope.model_dump(),
                "start_time": context.start_time,
                "end_time": context.end_time,
            }
        )
        state = WorkflowState(question=question, request=request, scope=scope, context=context)
        try:
            plan = planner.plan(state)
            validate_plan(plan)
            actual = plan.intent.value
            item = {
                "question": question,
                "expected": expected,
                "actual": actual,
                "plan": plan.model_dump(mode="json"),
                "passed": actual == expected,
            }
            if "failure rate" in question:
                item["passed"] &= plan.scenario.request.method.value == "failure_rate"
            if "repair duration" in question:
                item["passed"] &= plan.scenario.request.method.value == "repair_duration"
        except (ClarificationRequired, UnsupportedQuestion) as exc:
            actual = (
                "clarification_required"
                if isinstance(exc, ClarificationRequired)
                else "unsupported"
            )
            item = {
                "question": question,
                "expected": expected,
                "actual": actual,
                "message": str(exc),
                "passed": actual == expected,
            }
        except Exception as exc:
            item = {
                "question": question,
                "expected": expected,
                "actual": type(exc).__name__,
                "passed": False,
            }
        results.append(item)
        print(
            json.dumps({"expected": expected, "actual": item["actual"], "passed": item["passed"]}),
            flush=True,
        )
    return {"cases": results, "passed": all(r["passed"] for r in results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["planning", "combined", "knowledge"])
    parser.add_argument(
        "--audit", type=UUID, help="Prior investigation for isolated knowledge check"
    )
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Use a fresh report path")
    engine = None
    start = monotonic()
    try:
        configure_logging(get_settings().log_level)
        engine = create_db_engine()
        if args.mode == "planning":
            result = planning(engine)
        elif args.mode == "knowledge":
            if args.audit is None:
                parser.error("knowledge mode requires --audit")
            with engine.connect() as connection:
                saved = connection.scalar(
                    select(InvestigationAudit.state).where(InvestigationAudit.id == args.audit)
                )
            state = WorkflowState.model_validate(saved)
            captured = []

            class CapturingLLM:
                def generate(self, instruction, data, schema):
                    output = OpenAIStructuredLLM(get_settings()).generate(instruction, data, schema)
                    captured.append({"input": data, "output": output.model_dump(mode="json")})
                    return output

            try:
                output = KnowledgeAgent(engine, CapturingLLM()).run(
                    KnowledgeInput(
                        analytics=state.analytics,
                        stations=[state.analytics.overall.leading_candidate],
                        query=state.question[:1000],
                        limit=state.request.retrieval_limit,
                    )
                )
                result = {
                    "passed": True,
                    "knowledge": output.model_dump(mode="json"),
                    "captured": captured,
                }
            except ValueError as exc:
                # Agent policy errors contain no provider response or credentials.
                result = {
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc) if type(exc) is ValueError else "Provider unavailable",
                    "captured": captured,
                }
        else:
            request = InvestigationRequest.model_validate_json(
                Path("tests/fixtures/stage6-combined-request.json").read_text(encoding="utf-8")
            )
            response = InvestigationWorkflow(engine).run(request)
            components = [e.component for e in response.events]
            result = {
                "passed": response.outcome == "completed"
                and components
                == ["planner", "analytics", "knowledge", "simulation", "validation", "compose"],
                "response": response.model_dump(mode="json"),
            }
            print(
                json.dumps(
                    {
                        "outcome": response.outcome,
                        "components": components,
                        "audit_id": str(response.audit_id),
                    }
                ),
                flush=True,
            )
        result["elapsed_seconds"] = monotonic() - start
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
        print(
            json.dumps({"passed": result["passed"], "elapsed_seconds": result["elapsed_seconds"]})
        )
        return 0 if result["passed"] else 1
    except Exception as exc:
        print(f"Live acceptance failed ({type(exc).__name__}); no successful result is claimed.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
