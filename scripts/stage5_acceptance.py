"""Explicit live Stage 5 enrichment/probes; synthetic sources only, no Stage 6 work."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from sqlalchemy import select, text

from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.db.base import Base
from bottleneck_analyzer.db.models.production import (
    Dataset,
    FaultEvent,
    MaintenanceWorkOrder,
    SOPSection,
    SourceRecord,
    Station,
)
from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.domain.manufacturing import STATION_NAMES
from bottleneck_analyzer.retrieval.contracts import RetrievalRequest
from bottleneck_analyzer.retrieval.embeddings import CachedEmbedder, OpenAIEmbedder
from bottleneck_analyzer.retrieval.indexing import index_sources
from bottleneck_analyzer.retrieval.service import retrieve

DATASETS = ("sim-30day-baseline-v1", "sim-framing-validation-v1", "stage2-30day-v1")


def snapshot(engine) -> dict:
    """Compare source facts while allowing only the two derived embedding columns."""
    result = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            for name in sorted(Base.metadata.tables):
                value = "to_jsonb(t)"
                if name == "source_record":
                    value += "-'embedding'-'embedding_model'"
                row = connection.execute(
                    text(
                        "SELECT count(*),md5(coalesce(string_agg(md5(("
                        + value
                        + ")::text),'' ORDER BY id),'')) FROM \""
                        + name
                        + '" t'
                    )
                ).one()
                result[name] = {"rows": row[0], "source_facts_md5": row[1]}
    result["stage3_reports"] = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path("data/processed/stage3").glob("*.json")
    }
    return result


def eligible(connection, dataset_id):
    return (
        select(
            SourceRecord.id,
            SourceRecord.text_content,
            SourceRecord.embedding,
            SourceRecord.embedding_model,
        )
        .where(
            SourceRecord.dataset_id == dataset_id,
            SourceRecord.station_id.is_not(None),
            SourceRecord.text_content != "",
            (SourceRecord.system.in_(["CMMS", "Andon", "shift_notes"]))
            | (
                SourceRecord.id.in_(
                    select(SOPSection.source_record_id).where(SOPSection.dataset_id == dataset_id)
                )
            ),
        )
        .order_by(SourceRecord.id)
    )


def index(engine, provider, report_path: Path) -> dict:
    before = snapshot(engine)
    checkpoint = report_path.with_suffix(".before.json")
    with checkpoint.open("x", encoding="utf-8") as out:
        json.dump(before, out, indent=2)
    report = {
        "model_identity": provider.spec.identity,
        "datasets": {},
        "before_audit": str(checkpoint),
    }
    for name in DATASETS:
        with engine.connect() as connection:
            dataset_id = connection.scalar(select(Dataset.id).where(Dataset.name == name))
            if dataset_id is None:
                raise ValueError(f"Required dataset is missing: {name}")
            rows = connection.execute(eligible(connection, dataset_id)).mappings().all()
        ready, missing = [], []
        for row in rows:
            if row["embedding"] is not None or row["embedding_model"] is not None:
                if (
                    row["embedding"] is None
                    or row["embedding_model"] != provider.spec.identity
                    or len(row["embedding"]) != provider.spec.dimensions
                ):
                    raise ValueError("Incompatible existing embedding; no overwrite permitted")
                ready.append(row)
                if len(row["text_content"]) <= 2000:
                    provider.cache.setdefault(row["text_content"], list(row["embedding"]))
            else:
                missing.append(row["id"])
        total = 0
        for offset in range(0, len(missing), 50):
            with engine.begin() as connection:
                indexed = index_sources(
                    connection, dataset_id, missing[offset : offset + 50], provider
                )
            total += indexed["indexed"]
            print(
                json.dumps({"dataset": name, "newly_indexed": total, "eligible": len(rows)}),
                flush=True,
            )
        report["datasets"][name] = {
            "eligible": len(rows),
            "already_indexed": len(ready),
            "newly_indexed": total,
        }
    after = snapshot(engine)
    if after != before:
        raise ValueError("Source-fact preservation audit failed")
    report.update(
        {
            "source_facts_and_stage3_reports_unchanged": True,
            "after_audit": after,
            "provider_requests": provider.requests,
            "unique_texts_generated": provider.generated_texts,
        }
    )
    return report


def probe(engine, provider, cutoff: float) -> dict:
    """Calibration questions are labeled; inspect distances before choosing a cutoff."""
    questions = [
        ("robot_paraphrase", "sim-30day-baseline-v1", "Hemming", "Robot faults requiring repair"),
        (
            "broad_repair",
            "sim-30day-baseline-v1",
            "Hemming",
            "Equipment stopped and required maintenance repairs",
        ),
        (
            "electrical",
            "sim-30day-baseline-v1",
            "Hemming",
            "An electrical equipment failure was repaired",
        ),
        (
            "irrelevant_food",
            "sim-30day-baseline-v1",
            "Hemming",
            "How do I bake a chocolate birthday cake?",
        ),
        (
            "irrelevant_travel",
            "sim-30day-baseline-v1",
            "Hemming",
            "Find a hotel near the beach for a holiday",
        ),
        (
            "sop_reporting",
            "stage2-30day-v1",
            "Hemming",
            "What should staff record when a robot alarm occurs?",
        ),
        (
            "sop_approval",
            "stage2-30day-v1",
            "Hemming",
            "Who may authorize an equipment intervention?",
        ),
        ("framing", "sim-framing-validation-v1", "Framing", "Robot faults requiring repair"),
    ]
    results = []
    for label, dataset, station, query in questions:
        request = RetrievalRequest(
            dataset=dataset,
            stations=[station],
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-04T00:00:00Z" if "framing" in dataset else "2026-10-01T00:00:00Z",
            query=query,
            methods=["semantic"],
            limit=5,
            maximum_cosine_distance=cutoff,
        )
        result = retrieve(engine, request, embedder=provider)
        row = {
            "case": label,
            "request": request.model_dump(mode="json"),
            "diagnostics": result.diagnostics.model_dump(),
            "hits": [
                {
                    "source_id": str(e.source_record_id),
                    "text": e.text,
                    "station": e.station,
                    "system": e.source_system,
                    "section": e.section_sequence,
                    "version": e.document_version,
                    "similarity": e.scores["semantic_raw"],
                }
                for e in result.evidence
            ],
        }
        results.append(row)
        print(
            json.dumps(
                {
                    "case": label,
                    "hits": len(row["hits"]),
                    "top_similarity": row["hits"][0]["similarity"] if row["hits"] else None,
                }
            ),
            flush=True,
        )
    return {
        "maximum_cosine_distance": cutoff,
        "cases": results,
        "provider_requests": provider.requests,
    }


def validate(engine, provider) -> dict:
    fixtures = json.loads(
        Path("tests/fixtures/live-retrieval-quality.json").read_text(encoding="utf-8")
    )
    cases = list(fixtures["cases"])
    for station in STATION_NAMES:
        if station != "Hemming":
            cases.append(
                {
                    "name": f"station_scope:{station}",
                    "dataset": DATASETS[0],
                    "station": station,
                    "query": "Robot stopped; technicians performed a repair",
                    "expected_text": "robot_fault",
                }
            )
    provider.embed(list(dict.fromkeys(case["query"] for case in cases)))
    results = []
    for case in cases:
        request = RetrievalRequest(
            dataset=case["dataset"],
            stations=[case["station"]],
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-04T00:00:00Z"
            if "framing" in case["dataset"]
            else "2026-10-01T00:00:00Z",
            query=case["query"],
            methods=["semantic"],
            limit=5,
            **({"systems": case["systems"]} if "systems" in case else {}),
        )
        result = retrieve(engine, request, embedder=provider)
        passed = (
            result.diagnostics.methods_run == ["semantic"]
            and not result.diagnostics.unavailable
            and all(
                e.dataset_name == case["dataset"] and e.station == case["station"]
                for e in result.evidence
            )
        )
        if case.get("expected_empty"):
            passed = passed and not result.evidence
        else:
            passed = passed and len(result.evidence) >= case.get("minimum_hits", 1)
        if "expected_text" in case:
            passed = (
                passed
                and bool(result.evidence)
                and case["expected_text"] in result.evidence[0].text
            )
        if "expected_section" in case:
            passed = (
                passed
                and bool(result.evidence)
                and result.evidence[0].section_sequence == case["expected_section"]
            )
            passed = passed and all(e.document_version and e.document_id for e in result.evidence)
        results.append(
            {
                "name": case["name"],
                "passed": bool(passed),
                "request": request.model_dump(mode="json"),
                "diagnostics": result.diagnostics.model_dump(),
                "evidence": [e.model_dump(mode="json") for e in result.evidence],
            }
        )
        print(
            json.dumps(
                {
                    "case": case["name"],
                    "passed": bool(passed),
                    "hits": len(result.evidence),
                    "top_similarity": result.evidence[0].scores["semantic_raw"]
                    if result.evidence
                    else None,
                }
            ),
            flush=True,
        )
    with engine.connect() as connection:
        target = (
            connection.execute(
                select(
                    MaintenanceWorkOrder.id,
                    FaultEvent.id.label("fault_id"),
                    SourceRecord.text_content,
                    SourceRecord.id.label("source_id"),
                    SourceRecord.recorded_at,
                )
                .join(FaultEvent, FaultEvent.id == MaintenanceWorkOrder.fault_id)
                .join(SourceRecord, SourceRecord.id == MaintenanceWorkOrder.source_record_id)
                .join(Dataset, Dataset.id == MaintenanceWorkOrder.dataset_id)
                .join(Station, Station.id == MaintenanceWorkOrder.station_id)
                .where(
                    Dataset.name == DATASETS[0],
                    Station.name == "Hemming",
                    FaultEvent.category == "robot_fault",
                )
                .order_by(SourceRecord.recorded_at)
                .limit(1)
            )
            .mappings()
            .one()
        )
    request = RetrievalRequest(
        dataset=DATASETS[0],
        stations=["Hemming"],
        start_time="2026-09-01T00:00:00Z",
        end_time="2026-10-01T00:00:00Z",
        work_order_ids=[target["id"]],
        query=target["text_content"],
        limit=20,
    )
    hybrid = retrieve(engine, request, embedder=provider)
    merged = next((e for e in hybrid.evidence if e.source_record_id == target["source_id"]), None)
    passed = (
        not hybrid.diagnostics.unavailable
        and hybrid.diagnostics.methods_run == ["exact", "lexical", "semantic"]
        and merged is not None
        and set(merged.retrieval_methods) == {"exact", "lexical", "semantic"}
        and hybrid.evidence[0].relationship == "direct"
        and len({e.evidence_id for e in hybrid.evidence}) == len(hybrid.evidence)
    )
    results.append(
        {
            "name": "hybrid_exact_priority_and_dedup",
            "passed": bool(passed),
            "result": hybrid.model_dump(mode="json"),
        }
    )
    # End-exclusive timestamp boundary must exclude that source even on an exact request.
    boundary = retrieve(
        engine,
        request.model_copy(
            update={"end_time": target["recorded_at"], "methods": ["exact"], "query": ""}
        ),
        embedder=provider,
    )
    results.append(
        {
            "name": "half_open_timestamp_boundary",
            "passed": all(e.source_record_id != target["source_id"] for e in boundary.evidence),
        }
    )
    with engine.connect() as connection:
        foreign = connection.scalar(
            select(MaintenanceWorkOrder.id)
            .join(Dataset, Dataset.id == MaintenanceWorkOrder.dataset_id)
            .where(Dataset.name == DATASETS[1])
            .limit(1)
        )
    try:
        retrieve(
            engine, request.model_copy(update={"work_order_ids": [foreign]}), embedder=provider
        )
        rejected = False
    except ValueError:
        rejected = True
    results.append({"name": "foreign_dataset_identifier_rejected", "passed": rejected})
    return {
        "fixture_description": fixtures["description"],
        "cases": results,
        "passed": sum(row["passed"] for row in results),
        "total": len(results),
        "all_passed": all(row["passed"] for row in results),
        "provider_requests": provider.requests,
        "maximum_cosine_distance": request.maximum_cosine_distance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["index", "probe", "validate"])
    parser.add_argument("--cutoff", type=float, default=2)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("Use a fresh report path")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine()
    provider = CachedEmbedder(OpenAIEmbedder(get_settings()))
    started = time.perf_counter()
    try:
        if args.mode == "index":
            report = index(engine, provider, args.report)
        elif args.mode == "probe":
            report = probe(engine, provider, args.cutoff)
        else:
            report = validate(engine, provider)
        report["elapsed_seconds"] = time.perf_counter() - started
        with args.report.open("x", encoding="utf-8") as out:
            json.dump(report, out, indent=2)
        print(
            json.dumps({"report": str(args.report), "elapsed_seconds": report["elapsed_seconds"]})
        )
        return 0 if report.get("all_passed", True) else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
