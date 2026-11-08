"""Explicit derived-vector enrichment; never called during retrieval or startup."""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection

from bottleneck_analyzer.db.models.production import SOPDocument, SOPSection, SourceRecord
from bottleneck_analyzer.retrieval.chunking import chunks
from bottleneck_analyzer.retrieval.embeddings import Embedder, embed_texts, pool


def index_sources(
    connection: Connection, dataset_id: UUID, source_ids: list[UUID], embedder: Embedder
) -> dict[str, int]:
    """Caller explicitly authorizes/owns the transaction; immutable source fields stay intact.

    Only null embedding pairs can be populated. No automatic backfill, overwrite,
    dataset creation or commit. Stage 5 verification calls this only in isolated
    rollback-only schemas, preserving all development datasets byte-for-byte.
    """
    if not source_ids or len(source_ids) > 50 or len(set(source_ids)) != len(source_ids):
        raise ValueError("Select 1–50 unique source UUIDs explicitly")
    rows = (
        connection.execute(
            select(SourceRecord.__table__)
            .where(SourceRecord.dataset_id == dataset_id, SourceRecord.id.in_(source_ids))
            .order_by(SourceRecord.id)
        )
        .mappings()
        .all()
    )
    if {r["id"] for r in rows} != set(source_ids):
        raise ValueError("Embedding source is missing or outside selected dataset")
    sections = set(
        connection.scalars(
            select(SOPSection.source_record_id).where(
                SOPSection.dataset_id == dataset_id, SOPSection.source_record_id.in_(source_ids)
            )
        )
    )
    sectioned_parents = set(
        connection.scalars(
            select(SOPDocument.source_record_id)
            .join(SOPSection, SOPSection.document_id == SOPDocument.id)
            .where(
                SOPDocument.dataset_id == dataset_id,
                SOPSection.dataset_id == dataset_id,
                SOPDocument.source_record_id.in_(source_ids),
                func.length(func.trim(SOPSection.content)) > 0,
            )
        )
    )
    pending, skipped = [], 0
    for row in rows:
        if row["id"] in sectioned_parents:
            skipped += 1
            continue
        if row["embedding"] is not None or row["embedding_model"] is not None:
            if row["embedding_model"] != embedder.spec.identity or row["embedding"] is None:
                raise ValueError(
                    "Existing embedding metadata is incompatible; explicit replacement is required"
                )
            if len(row["embedding"]) != embedder.spec.dimensions:
                raise ValueError("Existing embedding dimension is incompatible")
            skipped += 1
            continue
        if not row["text_content"].strip():
            skipped += 1
            continue
        spans = chunks(
            row["id"],
            row["text_content"],
            sop=row["system"] == "SOP",
            section=row["id"] in sections,
        )
        if len(spans) > 64:
            raise ValueError("Fallback document exceeds 64 chunks; provide authored SOP sections")
        pending.append((row["id"], [c.text for c in spans]))
    texts = list(dict.fromkeys(text for _, spans in pending for text in spans))
    generated = {}
    for offset in range(0, len(texts), 64):
        batch = texts[offset : offset + 64]
        generated.update(zip(batch, embed_texts(embedder, batch), strict=True))
    enriched = []
    for source_id, spans in pending:
        vectors = [generated[part] for part in spans]
        vector = vectors[0] if len(vectors) == 1 else pool(vectors, embedder.spec)
        enriched.append((source_id, vector))
    # All provider calls/validation complete before any update; savepoint makes
    # a failed/raced write atomic even if the caller catches the exception.
    with connection.begin_nested():
        for source_id, vector in enriched:
            changed = connection.execute(
                update(SourceRecord)
                .where(
                    SourceRecord.dataset_id == dataset_id,
                    SourceRecord.id == source_id,
                    SourceRecord.embedding.is_(None),
                    SourceRecord.embedding_model.is_(None),
                )
                .values(embedding=vector, embedding_model=embedder.spec.identity)
            )
            if changed.rowcount != 1:
                raise ValueError("Embedding changed concurrently; retry without overwriting")
    return {"indexed": len(pending), "skipped": skipped}
