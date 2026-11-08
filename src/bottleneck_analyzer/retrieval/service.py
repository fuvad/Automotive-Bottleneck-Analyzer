"""Exact-first, bounded, read-only retrieval; never runs analytics or an agent."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from bottleneck_analyzer.analytics.contracts import AnalyticsResult, SegmentResult
from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.retrieval.chunking import chunks
from bottleneck_analyzer.retrieval.contracts import (
    CandidateContext,
    Diagnostics,
    Evidence,
    Relationship,
    RetrievalRequest,
    RetrievalResult,
)
from bottleneck_analyzer.retrieval.embeddings import (
    Embedder,
    EmbeddingUnavailable,
    OpenAIEmbedder,
    embed_texts,
)
from bottleneck_analyzer.retrieval.evidence import assess, content_warnings, merge_results
from bottleneck_analyzer.retrieval.repository import RetrievalRepository


def retrieve(
    engine: Engine,
    request: RetrievalRequest,
    *,
    embedder: Embedder | None = None,
    contexts: list[CandidateContext] | None = None,
) -> RetrievalResult:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            return retrieve_connection(connection, request, embedder=embedder, contexts=contexts)


def retrieve_connection(
    connection: Connection,
    request: RetrievalRequest,
    *,
    embedder: Embedder | None = None,
    contexts: list[CandidateContext] | None = None,
) -> RetrievalResult:
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    repo = RetrievalRepository(connection, request)
    for context in contexts or []:
        if (
            context.dataset_id != repo.dataset["id"]
            or context.station not in repo.stations.values()
            or context.start_time != request.start_time
            or context.end_time != request.end_time
        ):
            raise ValueError(
                "Candidate context does not match retrieval dataset, station and period"
            )
    diagnostics = Diagnostics(filters=request.model_dump(mode="json"))
    _, root_links = repo.resolve()
    methods: list[tuple[str, list[dict]]] = []
    for method in ("exact", "lexical"):
        if method not in request.methods:
            continue
        if method == "lexical" and not request.query.strip():
            diagnostics.unavailable[method] = "No lexical query supplied"
            continue
        try:
            # A failed optional SQL method must not abort successful exact results.
            with connection.begin_nested():
                rows = repo.exact() if method == "exact" else repo.lexical()
            methods.append((method, rows))
            diagnostics.methods_run.append(method)
            diagnostics.match_counts[method] = len(rows)
        except SQLAlchemyError:
            diagnostics.unavailable[method] = "Database retrieval method failed"
    if "semantic" in request.methods:
        try:
            if not request.query.strip():
                raise EmbeddingUnavailable("No semantic query supplied")
            provider = embedder or OpenAIEmbedder(get_settings())
            with connection.begin_nested():
                count = repo.vector_count(provider.spec)
            if not count:
                raise EmbeddingUnavailable("No compatible stored embeddings in the selected scope")
            vector = embed_texts(provider, [request.query])[0]
            with connection.begin_nested():
                rows = repo.semantic(vector, provider.spec)
            methods.append(("semantic", rows))
            diagnostics.methods_run.append("semantic")
            diagnostics.match_counts["semantic"] = len(rows)
        except EmbeddingUnavailable as exc:
            diagnostics.unavailable["semantic"] = str(exc)
        except SQLAlchemyError:
            diagnostics.unavailable["semantic"] = "Database semantic search failed"
    all_rows = {r["id"]: r for _, rows in methods for r in rows}
    with connection.begin_nested():
        links = repo.relationships(list(all_rows)) if all_rows else []
    if len(links) > 1000:
        diagnostics.warnings.append("Relationship details truncated at 1,000 links")
        links = links[:1000]
    # Keep the direction/type of original graph edges, even if their other source
    # was not selected as a passage. Endpoint IDs alone are not source disclosures.
    graph = {r["id"]: r for r in root_links + links}
    items = []
    for method, rows in methods:
        for rank, row in enumerate(rows, 1):
            source_links = [
                Relationship(
                    relationship=link["relationship"],
                    basis=link["basis"],
                    from_source_id=link["from_record_id"],
                    to_source_id=link["to_record_id"],
                )
                for link in graph.values()
                if row["id"] in (link["from_record_id"], link["to_record_id"])
            ]
            target_links = [
                link
                for link in source_links
                if link.from_source_id in repo.params["seeds"]
                or link.to_source_id in repo.params["seeds"]
            ]
            inferred_to_target = any(link.relationship == "inferred" for link in target_links)
            direct_to_target = any(link.relationship == "direct" for link in target_links)
            direct = direct_to_target or (
                not inferred_to_target
                and (
                    row["incident_id"] is not None
                    or row["incident_id"] in repo.params["root_incidents"]
                    or row["work_order_id"] in request.work_order_ids
                    or row["id"] in request.source_record_ids
                )
            )
            relation = "direct" if direct else "inferred"
            basis = (
                "Explicit incident/work-order/source relationship; causation remains unconfirmed"
                if direct
                else "; ".join(
                    link.basis for link in target_links if link.relationship == "inferred"
                )
                if inferred_to_target
                else "Selected station/time metadata and search relevance; no target incident link"
            )
            # Fallback spans are source-level search hits; return only bounded
            # best lexical spans rather than dumping an arbitrarily long document.
            spans = chunks(
                row["id"],
                row["passage"],
                sop=row["system"] == "SOP",
                section=row["section_id"] is not None,
            )
            if len(spans) > 1:
                terms = request.query.lower().split()
                spans = sorted(
                    spans, key=lambda c: (-sum(t in c.text.lower() for t in terms), c.start)
                )[:3]
            for span in spans:
                item = Evidence(
                    evidence_id=span.evidence_id,
                    dataset_id=repo.dataset["id"],
                    dataset_name=repo.dataset["name"],
                    provenance=repo.dataset["provenance"],
                    source_record_id=row["id"],
                    source_system=row["system"],
                    source_id=row["source_id"],
                    source_type=row["source_type"],
                    original_path=row["original_path"],
                    recorded_at=row["recorded_at"],
                    station_id=row["station_id"],
                    station=row["station_name"],
                    text=span.text,
                    original_text=row["text_content"],
                    text_basis="original_source_text"
                    if row["text_content"]
                    else "sop_content"
                    if row["document_id"]
                    else "normalized_record_fields",
                    raw_metadata=row["raw"],
                    incident_id=row["incident_id"],
                    work_order_id=row["work_order_id"],
                    recorded_cause=row["recorded_cause"],
                    historian_quality=row["historian_quality"],
                    historian_value=row["historian_value"],
                    document_id=row["document_id"],
                    document_version=row["document_version"],
                    document_effective_at=row["document_effective_at"],
                    section_id=row["section_id"],
                    section_sequence=row["section_sequence"],
                    text_start=span.start,
                    text_end=span.end,
                    retrieval_methods=[method],
                    scores={method: float(rank), method + "_raw": row["retrieval_score"]},
                    relationship=relation,
                    relationship_basis=basis,
                    links=source_links,
                )
                item.warnings = content_warnings(item)
                items.append(item)
    merged, unique = merge_results(items, request.limit)
    diagnostics.unique_before_limit = unique
    diagnostics.returned = len(merged)
    diagnostics.duplicates_merged = len(items) - unique
    diagnostics.truncated = unique > request.limit or any(
        len(rows) == request.limit * 3 for _, rows in methods
    )
    if diagnostics.unavailable:
        diagnostics.warnings.append(
            "Partial retrieval: inspect unavailable methods before interpreting coverage"
        )
    if repo.dataset["config"].get("sop_reference_dataset"):
        diagnostics.warnings.append(
            "SOPs belong to the explicitly referenced dataset; no cross-dataset fallback performed"
        )
    return RetrievalResult(
        dataset_id=repo.dataset["id"],
        dataset_name=repo.dataset["name"],
        provenance=repo.dataset["provenance"],
        content_hash=repo.dataset["content_hash"],
        request=request,
        evidence=merged,
        assessments=assess(list(repo.stations.values()), merged, contexts or []),
        diagnostics=diagnostics,
    )


def request_from_analytics(
    result: AnalyticsResult,
    *,
    stations: list[str],
    query: str,
    segment: SegmentResult | None = None,
    limit: int = 20,
) -> tuple[RetrievalRequest, list[CandidateContext]]:
    selected = segment or result.overall
    if selected.key != "overall" and not any(selected == s for s in result.segments):
        raise ValueError("Segment does not belong to the supplied analytics result")
    candidates = {c.station: c for c in selected.candidates}
    if set(stations) - set(candidates):
        raise ValueError("Requested station is absent from this analytics result")
    contexts = [
        CandidateContext(
            station=name,
            dataset_id=result.dataset_id,
            start_time=selected.start_time,
            end_time=selected.end_time,
            model=selected.model,
            aggregate_ids=candidates[name].aggregate_ids,
            indicators=candidates[name].indicators,
            supporting_indicators=candidates[name].supporting_evidence,
            conflicting_indicators=candidates[name].contradicting_evidence,
            sample_strength=candidates[name].strength,
        )
        for name in stations
    ]
    sources = sorted(
        {
            UUID(e.evidence_id)
            for s in selected.stations
            if s.station in stations
            for r in s.references
            for e in r.samples
        },
        key=str,
    )
    return RetrievalRequest(
        dataset=result.dataset_name,
        stations=stations,
        start_time=selected.start_time,
        end_time=selected.end_time,
        source_record_ids=sources,
        query=query,
        limit=limit,
        utc_hours=[selected.utc_hour] if selected.utc_hour is not None else result.scope.utc_hours,
        shift=result.scope.shift,
        shift_id=selected.shift_id or result.scope.shift_id,
    ), contexts
