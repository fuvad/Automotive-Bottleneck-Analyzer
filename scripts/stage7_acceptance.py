"""Read-only saved API acceptance and exact preservation comparison. No model/simulation runs."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text

from bottleneck_analyzer.db.session import create_db_engine
from bottleneck_analyzer.main import app


def snapshot() -> dict:
    files = {}
    root = Path.cwd()
    for folder in ("src", "alembic", "data/processed/stage3"):
        for path in (root / folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    for name in ("docs/implementation-plan.md", "pyproject.toml", "poetry.lock", ".env"):
        path = root / name
        if path.exists():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"files": files, "tables": {}}
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            tables = connection.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            ).all()
            for name in tables:
                safe = name.replace('"', '""')
                row = connection.execute(
                    text(
                        "SELECT count(*), md5(string_agg(h, '' ORDER BY h)) FROM "
                        f'(SELECT md5(to_jsonb(t)::text) h FROM public."{safe}" t) q'
                    )
                ).one()
                result["tables"][name] = {"count": row[0], "hash": row[1]}
            result["embeddings"] = connection.scalar(
                text("SELECT count(*) FROM source_record WHERE embedding IS NOT NULL")
            )
            result["temporary_schemas"] = connection.scalar(
                text("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'stage2_test_%'")
            )
    finally:
        engine.dispose()
    return result


def saved_acceptance(identifier: UUID) -> dict:
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        health = client.get("/health/database")
        datasets = client.get("/api/datasets")
        progress = client.get(f"/api/investigations/{identifier}")
        response = client.get(f"/api/investigations/{identifier}/result")
        response.raise_for_status()
        result = response.json()
        return {
            "saved_audit": str(identifier),
            "mode": "read_only_existing_result",
            "database_health": health.json(),
            "dataset_count": len(datasets.json()),
            "status_http": progress.status_code,
            "result_http": response.status_code,
            "final_confirmed": progress.json()["final_confirmed"],
            "outcome": result["outcome"],
            "result_bytes": len(response.content),
            "historical_jph": result["historical"]["historical_jph"],
            "simulated_baseline_mean": result["simulation"]["baseline"]["mean"],
            "evidence_records": len(result["evidence"]["records"]),
            "events": [e["component"] for e in result["events"]],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--saved-audit", type=UUID)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Use a fresh report path")
    result = {"snapshot": snapshot()}
    if args.before:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        before = before.get("snapshot", before)
        after = result["snapshot"]
        changed = [
            name
            for name, digest in before["files"].items()
            if name != "src/bottleneck_analyzer/main.py"
            and not name.startswith("src/bottleneck_analyzer/api/")
            and after["files"].get(name) != digest
        ]
        result["preservation"] = {
            "protected_files_unchanged": not changed,
            "changed_protected_files": changed,
            "all_original_tables_and_audits_unchanged": before["tables"] == after["tables"],
            "embedding_count_unchanged": before["embeddings"] == after["embeddings"],
            "no_test_schemas": after["temporary_schemas"] == 0,
        }
    if args.saved_audit:
        result["saved_api_acceptance"] = saved_acceptance(args.saved_audit)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    checks = result.get("preservation", {})
    passed = all(v for k, v in checks.items() if k != "changed_protected_files")
    print(
        json.dumps(
            {
                "passed": passed,
                "preservation": checks,
                "saved_api_acceptance": result.get("saved_api_acceptance"),
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
