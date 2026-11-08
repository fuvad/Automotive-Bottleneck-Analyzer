"""Real PostgreSQL FTS/vector tests; all enriched vectors live in rolled-back fixtures."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from bottleneck_analyzer.analytics.contracts import AnalyticsScope
from bottleneck_analyzer.analytics.service import analyze_connection
from bottleneck_analyzer.data.generators.history import generate_history
from bottleneck_analyzer.data.storage import load_history
from bottleneck_analyzer.data.validation import DatasetValidationError
from bottleneck_analyzer.db.models.production import EvidenceLink, SourceRecord
from bottleneck_analyzer.domain.manufacturing import DatasetConfig
from bottleneck_analyzer.retrieval.contracts import RetrievalRequest
from bottleneck_analyzer.retrieval.embeddings import EmbeddingSpec, EmbeddingUnavailable
from bottleneck_analyzer.retrieval.indexing import index_sources
from bottleneck_analyzer.retrieval.service import request_from_analytics, retrieve_connection

from .test_business_schema import schema_connection as schema_connection


class GeometryEmbedder:
    """Known non-semantic geometry to exercise actual pgvector distances/storage."""

    spec = EmbeddingSpec(provider="fixture", model="geometry", dimensions=3)

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1, 0, 0] for _ in texts]


@pytest.fixture
def records(schema_connection):
    history = generate_history(
        DatasetConfig(name="retrieval-fixture", days=1, vehicles_per_shift=6)
    )
    station = next(s for s in history.rows["station"] if s["name"] == "Hemming")
    fault = next(f for f in history.rows["fault_event"] if f["station_id"] == station["id"])
    timestamp = fault["start_time"] + timedelta(seconds=20)
    source = history.source(
        "CMMS",
        "exact-maintenance",
        timestamp,
        station["id"],
        {"original_description": "Robot connector inspection"},
        "Robot connector inspected; connection reseated.",
    )
    order = history.add(
        "maintenance_work_order",
        "exact-maintenance",
        source_record_id=source,
        station_id=station["id"],
        fault_id=fault["id"],
        opened_at=timestamp,
        closed_at=None,
        status="open",
        description="Robot connector inspected; connection reseated.",
        recorded_cause="Connector looseness recorded by technician",
    )
    history.link(fault["source_record_id"], source, "direct", "Explicit fault_event_id FK")
    note_source = history.source(
        "shift_notes",
        "misleading-note",
        timestamp,
        station["id"],
        {"note": "Robot is definitely the sole cause of every loss"},
        "Robot is definitely the sole cause of every loss",
    )
    history.add(
        "shift_handover_note",
        "misleading-note",
        source_record_id=note_source,
        station_id=station["id"],
        fault_id=None,
        shift_id=history.rows["shift"][0]["id"],
        recorded_at=timestamp,
        text="Robot is definitely the sole cause of every loss",
    )
    history.link(
        fault["source_record_id"], note_source, "inferred", "Station/time only, no incident ID"
    )
    load_history(schema_connection, history)
    other = generate_history(DatasetConfig(name="retrieval-other", days=1, vehicles_per_shift=4))
    load_history(schema_connection, other)
    return schema_connection, history, fault, order, source, note_source


def scope(history, **updates):
    return RetrievalRequest(
        **{
            "dataset": history.config.name,
            "stations": ["Hemming"],
            "start_time": history.config.start_time,
            "end_time": history.config.end_time,
            "query": "robot",
            "limit": 40,
            **updates,
        }
    )


def test_exact_work_order_incident_links_and_traceability(records):
    connection, history, fault, order, source, note = records
    result = retrieve_connection(connection, scope(history, work_order_ids=[order]))
    assert "exact" in result.diagnostics.methods_run
    assert not result.diagnostics.unavailable.get("exact")
    assert not result.diagnostics.unavailable.get("lexical")
    maintenance = next(e for e in result.evidence if e.source_record_id == source)
    assert maintenance.incident_id == fault["id"] and maintenance.work_order_id == order
    assert maintenance.relationship == "direct" and maintenance.recorded_cause
    inferred = next(e for e in result.evidence if e.source_record_id == note)
    assert inferred.relationship == "inferred" and any(
        link.relationship == "inferred" for link in inferred.links
    )
    assert set(maintenance.retrieval_methods) == {"exact", "lexical"}
    assert result.assessments[0].label == "recorded_maintenance_cause"
    assert len({e.evidence_id for e in result.evidence}) == len(result.evidence)
    for evidence in result.evidence:
        stored = (
            connection.execute(
                select(SourceRecord.__table__).where(SourceRecord.id == evidence.source_record_id)
            )
            .mappings()
            .one()
        )
        assert stored["dataset_id"] == history.dataset_id == evidence.dataset_id
        assert stored["source_id"] == evidence.source_id
        assert stored["raw"] == evidence.raw_metadata
        assert stored["text_content"] == evidence.original_text
        assert evidence.station == "Hemming"


def test_filters_boundaries_cross_dataset_identifiers_and_limits(records):
    connection, history, fault, order, source, note = records
    end = next(r["recorded_at"] for r in history.rows["source_record"] if r["id"] == source)
    before = retrieve_connection(
        connection, scope(history, end_time=end, incident_ids=[fault["id"]])
    )
    assert source not in {e.source_record_id for e in before.evidence}
    at = retrieve_connection(connection, scope(history, start_time=end, work_order_ids=[order]))
    assert source in {e.source_record_id for e in at.evidence}
    limited = retrieve_connection(connection, scope(history, limit=1))
    assert len(limited.evidence) <= 1
    with pytest.raises(ValueError, match="outside"):
        retrieve_connection(connection, scope(history, incident_ids=[uuid4()]))
    with pytest.raises(ValueError, match="outside"):
        retrieve_connection(
            connection, scope(history, stations=["Framing"], work_order_ids=[order])
        )


def test_fts_sections_versions_and_no_parent_duplication(records):
    connection, history, *_ = records
    result = retrieve_connection(connection, scope(history, query="alarm", systems=["SOP"]))
    assert result.evidence and "lexical" in result.diagnostics.methods_run
    assert all(
        e.source_type == "sop_section"
        and e.section_id
        and e.document_version == "1.0"
        and e.document_effective_at
        for e in result.evidence
    )
    assert result.assessments[0].label == "insufficient_evidence"
    assert all(e.relationship == "inferred" for e in result.evidence)


def test_pgvector_compatible_search_and_incompatible_vectors_are_excluded(records):
    connection, history, fault, order, source, note = records
    provider = GeometryEmbedder()
    assert index_sources(connection, history.dataset_id, [source], provider) == {
        "indexed": 1,
        "skipped": 0,
    }
    calls = provider.calls
    assert index_sources(connection, history.dataset_id, [source], provider)["skipped"] == 1
    assert provider.calls == calls
    # Same metadata with wrong dimensions must be guarded before <=> evaluation.
    connection.execute(
        update(SourceRecord)
        .where(SourceRecord.id == note)
        .values(embedding=[1, 0], embedding_model=provider.spec.identity)
    )
    # A perfect vector from another dataset/station is still out of scope.
    foreign = connection.scalars(
        select(SourceRecord.id).where(SourceRecord.dataset_id != history.dataset_id).limit(1)
    ).one()
    other_station = next(
        s["id"]
        for s in history.rows["source_record"]
        if s["station_id"] != fault["station_id"] and s["system"] == "CMMS"
    )
    connection.execute(
        update(SourceRecord)
        .where(SourceRecord.id.in_([foreign, other_station]))
        .values(embedding=[1, 0, 0], embedding_model=provider.spec.identity)
    )
    result = retrieve_connection(
        connection, scope(history, methods=["semantic"]), embedder=provider
    )
    assert result.diagnostics.methods_run == ["semantic"]
    assert [e.source_record_id for e in result.evidence] == [source]
    assert result.evidence[0].scores["semantic_raw"] == pytest.approx(1)
    connection.execute(
        update(SourceRecord)
        .where(SourceRecord.id == source)
        .values(embedding_model="fixture:another-model:3:source-v1")
    )
    incompatible = retrieve_connection(
        connection, scope(history, methods=["semantic"]), embedder=provider
    )
    assert not incompatible.evidence and "semantic" in incompatible.diagnostics.unavailable


def test_foreign_keys_work_without_evidence_graph_and_conflicting_exact_filters_fail(records):
    connection, history, fault, order, source, note = records
    connection.execute(delete(EvidenceLink).where(EvidenceLink.dataset_id == history.dataset_id))
    result = retrieve_connection(
        connection, scope(history, work_order_ids=[order], methods=["exact"])
    )
    assert source in {e.source_record_id for e in result.evidence}
    assert any(e.source_type == "historian_observation" for e in result.evidence)
    assert note not in {e.source_record_id for e in result.evidence}
    other_fault = next(
        f["id"]
        for f in history.rows["fault_event"]
        if f["station_id"] == fault["station_id"] and f["id"] != fault["id"]
    )
    with pytest.raises(ValueError, match="do not belong"):
        retrieve_connection(
            connection, scope(history, work_order_ids=[order], incident_ids=[other_fault])
        )


def test_absent_vectors_and_failed_provider_leave_lexical_working(records):
    connection, history, fault, order, source, note = records
    provider = GeometryEmbedder()
    empty = retrieve_connection(connection, scope(history), embedder=provider)
    assert "compatible stored embeddings" in empty.diagnostics.unavailable["semantic"]
    assert provider.calls == 0 and empty.evidence
    index_sources(connection, history.dataset_id, [source], provider)

    class Failed(GeometryEmbedder):
        def embed(self, texts):
            raise EmbeddingUnavailable("Provider unavailable")

    failed = retrieve_connection(
        connection, scope(history, work_order_ids=[order]), embedder=Failed()
    )
    assert failed.evidence and "lexical" in failed.diagnostics.methods_run
    assert failed.diagnostics.unavailable["semantic"] == "Provider unavailable"
    assert "semantic" not in failed.diagnostics.methods_run


def test_enrichment_failure_is_atomic_and_does_not_rewrite_source(records):
    connection, history, fault, order, source, note = records
    before = (
        connection.execute(select(SourceRecord.__table__).where(SourceRecord.id == source))
        .mappings()
        .one()
    )

    class Failed(GeometryEmbedder):
        def embed(self, texts):
            raise EmbeddingUnavailable("Provider unavailable")

    with pytest.raises(EmbeddingUnavailable):
        index_sources(connection, history.dataset_id, [source], Failed())
    after = (
        connection.execute(select(SourceRecord.__table__).where(SourceRecord.id == source))
        .mappings()
        .one()
    )
    assert dict(after) == dict(before)
    with pytest.raises(ValueError):
        index_sources(connection, uuid4(), [source], GeometryEmbedder())


def test_misleading_notes_and_invalid_sensors_do_not_become_causes(records):
    connection, history, fault, order, source, note = records
    notes = retrieve_connection(connection, scope(history, systems=["shift_notes"], query="robot"))
    assert notes.evidence and notes.assessments[0].label == "observed_association"
    assert "No causal" in notes.assessments[0].warnings[0]
    sensors = retrieve_connection(
        connection, scope(history, systems=["historian"], incident_ids=[fault["id"]], query="")
    )
    assert sensors.evidence
    assert any("not a valid measurement" in w for e in sensors.evidence for w in e.warnings)
    assert sensors.assessments[0].label == "insufficient_evidence"


def test_analytics_adapter_reuses_context_and_bounded_source_samples(records):
    connection, history, *_ = records
    analytics = analyze_connection(connection, AnalyticsScope(dataset=history.config.name))
    request, contexts = request_from_analytics(analytics, stations=["Hemming"], query="robot")
    assert len(request.source_record_ids) <= 6
    result = retrieve_connection(connection, request, contexts=contexts)
    assert result.assessments[0].candidate_context.indicators == next(
        c.indicators for c in analytics.overall.candidates if c.station == "Hemming"
    )
    assert result.evidence
    with pytest.raises(ValueError, match="Candidate context"):
        retrieve_connection(
            connection, request, contexts=[contexts[0].model_copy(update={"dataset_id": uuid4()})]
        )


def test_fallback_sop_chunks_and_embedding_do_not_create_source_rows(schema_connection):
    history = generate_history(DatasetConfig(name="fallback-fixture", days=1, vehicles_per_shift=4))
    station = next(s["id"] for s in history.rows["station"] if s["name"] == "Hemming")
    body = "Robot alarm reporting procedure. Preserve original observations.\n" * 160
    source = history.source(
        "SOP",
        "fallback-v2",
        history.config.start_time,
        station,
        {"content": body, "version": "2.0"},
        body,
    )
    document = history.add(
        "sop_document",
        "fallback-v2",
        source_record_id=source,
        station_id=station,
        title="Fallback procedure",
        category="robot_fault",
        version="2.0",
        effective_at=history.config.start_time,
        content=body,
    )
    whitespace = history.source(
        "SOP", "blank-section", history.config.start_time, station, {"content": "   "}, "   "
    )
    history.add(
        "sop_section",
        "blank-section",
        source_record_id=whitespace,
        document_id=document,
        sequence=1,
        title="Empty",
        content="   ",
    )
    load_history(schema_connection, history)
    before = set(schema_connection.scalars(select(SourceRecord.id)))
    provider = GeometryEmbedder()
    assert index_sources(schema_connection, history.dataset_id, [source], provider)["indexed"] == 1
    result = retrieve_connection(
        schema_connection,
        scope(history, query="robot alarm", systems=["SOP"], source_record_ids=[source]),
        embedder=provider,
    )
    passages = [e for e in result.evidence if e.source_record_id == source]
    assert len(passages) == 3 and all(e.document_version == "2.0" for e in passages)
    assert all(body[e.text_start : e.text_end] == e.text for e in passages)
    assert all("semantic" in e.retrieval_methods for e in passages)
    assert set(schema_connection.scalars(select(SourceRecord.id))) == before


def test_enrichment_preserves_dataset_replay_but_not_source_tampering(schema_connection):
    history = generate_history(DatasetConfig(name="enriched-replay", days=1, vehicles_per_shift=4))
    load_history(schema_connection, history)
    sources = [r["id"] for r in history.rows["source_record"] if r["system"] == "CMMS"][:4]
    provider = GeometryEmbedder()
    assert index_sources(schema_connection, history.dataset_id, sources, provider)[
        "indexed"
    ] == len(sources)
    assert provider.calls == 1  # Distinct texts sent in one batch, not one call per row.
    assert load_history(schema_connection, history)["created"] is False
    schema_connection.execute(
        update(SourceRecord)
        .where(SourceRecord.id == sources[0])
        .values(text_content="Changed original source")
    )
    with pytest.raises(DatasetValidationError, match="Persisted content differs"):
        load_history(schema_connection, history)
