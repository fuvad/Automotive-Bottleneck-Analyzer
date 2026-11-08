"""Fixed, parameterized PostgreSQL searches over one explicitly selected dataset."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from bottleneck_analyzer.db.models.production import Dataset, Shift, SourceRecord, Station
from bottleneck_analyzer.retrieval.contracts import RetrievalRequest
from bottleneck_analyzer.retrieval.embeddings import EmbeddingSpec, validate_vector

RECORDS = """
records AS (
 SELECT s.*,st.name AS station_name,
   coalesce(f.id,m.fault_id,a.fault_id,n.fault_id,h.fault_id) AS incident_id,
   m.id AS work_order_id,m.recorded_cause,h.quality AS historian_quality,
   h.value AS historian_value,
   coalesce(sec.document_id,doc.id) AS document_id,sd.version AS document_version,
   sd.effective_at AS document_effective_at,sec.id AS section_id,sec.sequence AS section_sequence,
   CASE WHEN sec.id IS NOT NULL THEN 'sop_section' WHEN doc.id IS NOT NULL THEN 'sop_document'
        WHEN m.id IS NOT NULL THEN 'maintenance_work_order' WHEN a.id IS NOT NULL THEN 'andon_event'
        WHEN n.id IS NOT NULL THEN 'shift_handover_note'
        WHEN h.id IS NOT NULL THEN 'historian_observation'
        WHEN f.id IS NOT NULL THEN 'fault_event' ELSE s.system END AS source_type,
   coalesce(nullif(s.text_content,''),sec.content,doc.content,m.description,a.remarks,n.text,
       CASE WHEN h.id IS NOT NULL THEN concat(h.measurement_name,': ',h.value,' ',h.unit,
                                               '; quality=',h.quality) END,
       CASE WHEN f.id IS NOT NULL THEN concat(f.category,' ',f.fault_code,' ',f.equipment_id) END,
       '') AS passage
 FROM source_record s
 JOIN station st ON st.id=s.station_id AND st.dataset_id=:dataset_id
 LEFT JOIN fault_event f ON f.source_record_id=s.id AND f.dataset_id=:dataset_id
 LEFT JOIN maintenance_work_order m ON m.source_record_id=s.id AND m.dataset_id=:dataset_id
 LEFT JOIN andon_event a ON a.source_record_id=s.id AND a.dataset_id=:dataset_id
 LEFT JOIN shift_handover_note n ON n.source_record_id=s.id AND n.dataset_id=:dataset_id
 LEFT JOIN historian_observation h ON h.source_record_id=s.id AND h.dataset_id=:dataset_id
 LEFT JOIN sop_section sec ON sec.source_record_id=s.id AND sec.dataset_id=:dataset_id
 LEFT JOIN sop_document doc ON doc.source_record_id=s.id AND doc.dataset_id=:dataset_id
 LEFT JOIN sop_document sd ON sd.id=coalesce(sec.document_id,doc.id) AND sd.dataset_id=:dataset_id
 WHERE s.dataset_id=:dataset_id AND s.station_id=ANY(CAST(:stations AS uuid[]))
   AND s.system=ANY(CAST(:systems AS text[]))
   AND ((s.system<>'SOP' AND s.recorded_at>=:start AND s.recorded_at<:end
         AND (:all_hours OR extract(hour FROM s.recorded_at AT TIME ZONE 'UTC')::int
                               =ANY(CAST(:hours AS int[])))
         AND (:all_shifts OR EXISTS(SELECT 1 FROM shift sh WHERE sh.dataset_id=:dataset_id
             AND s.recorded_at>=sh.start_time AND s.recorded_at<sh.end_time
             AND (CAST(:shift_name AS text) IS NULL OR sh.name=:shift_name)
             AND (CAST(:shift_id AS uuid) IS NULL OR sh.id=CAST(:shift_id AS uuid)))))
      OR (s.system='SOP' AND sd.effective_at<:end))
   AND (doc.id IS NULL OR NOT EXISTS(SELECT 1 FROM sop_section se
         WHERE se.dataset_id=:dataset_id AND se.document_id=doc.id AND length(trim(se.content))>0))
   AND (:no_incidents OR coalesce(f.id,m.fault_id,a.fault_id,n.fault_id,h.fault_id)
                         =ANY(CAST(:incidents AS uuid[])) OR s.id=ANY(CAST(:related AS uuid[])))
   AND (:no_orders OR m.id=ANY(CAST(:orders AS uuid[]))
        OR coalesce(f.id,m.fault_id,a.fault_id,n.fault_id,h.fault_id)
           =ANY(CAST(:root_incidents AS uuid[])) OR s.id=ANY(CAST(:related AS uuid[])))
)
"""


class RetrievalRepository:
    def __init__(self, connection: Connection, request: RetrievalRequest):
        self.connection = connection
        self.request = request
        dataset = connection.execute(
            select(Dataset.__table__).where(Dataset.name == request.dataset)
        )
        self.dataset = dataset.mappings().one_or_none()
        if self.dataset is None:
            raise ValueError("Requested retrieval dataset does not exist")
        self.dataset = dict(self.dataset)
        if (
            request.start_time < self.dataset["start_time"]
            or request.end_time > self.dataset["end_time"]
        ):
            raise ValueError("Retrieval period must be inside the selected dataset")
        rows = connection.execute(
            select(Station.id, Station.name).where(Station.dataset_id == self.dataset["id"])
        ).all()
        requested_names, requested_ids = set(request.stations), set(request.station_ids)
        if requested_names - {r.name for r in rows} or requested_ids - {r.id for r in rows}:
            raise ValueError("Candidate station does not belong to this dataset")
        self.stations = {
            r.id: r.name for r in rows if r.name in requested_names or r.id in requested_ids
        }
        if request.shift_id and not connection.scalar(
            select(Shift.id).where(
                Shift.dataset_id == self.dataset["id"], Shift.id == request.shift_id
            )
        ):
            raise ValueError("Dated shift does not belong to this dataset")
        self.params = {
            "dataset_id": self.dataset["id"],
            "stations": list(self.stations),
            "systems": request.systems,
            "start": request.start_time,
            "end": request.end_time,
            "all_hours": not request.utc_hours,
            "hours": request.utc_hours,
            "all_shifts": not (request.shift or request.shift_id),
            "shift_name": request.shift,
            "shift_id": request.shift_id,
            "incidents": request.incident_ids,
            "orders": request.work_order_ids,
            "sources": request.source_record_ids,
            "related": [],
            "no_incidents": not request.incident_ids,
            "no_orders": not request.work_order_ids,
            "query": request.query,
            "limit": request.limit * 3,
        }

    def query(self, sql: str) -> list[dict]:
        return [dict(row) for row in self.connection.execute(text(sql), self.params).mappings()]

    def resolve(self) -> tuple[list[UUID], list[dict]]:
        """Resolve source samples/FKs before either broader search; no inferred promotion."""
        for table, key, identifiers in (
            ("fault_event", "incidents", self.request.incident_ids),
            ("maintenance_work_order", "orders", self.request.work_order_ids),
            ("source_record", "sources", self.request.source_record_ids),
        ):
            if identifiers:
                # Table/key are constants above, never source text or request SQL.
                valid = self.query(
                    f"SELECT id FROM {table} WHERE dataset_id=:dataset_id "
                    f"AND station_id=ANY(CAST(:stations AS uuid[])) "
                    f"AND id=ANY(CAST(:{key} AS uuid[]))"
                )
                if {r["id"] for r in valid} != set(identifiers):
                    raise ValueError(
                        "An exact identifier is missing or outside the dataset/stations"
                    )
        if self.request.incident_ids and self.request.work_order_ids:
            orders = self.query(
                "SELECT fault_id FROM maintenance_work_order WHERE "
                "dataset_id=:dataset_id AND id=ANY(CAST(:orders AS uuid[]))"
            )
            if any(r["fault_id"] not in self.request.incident_ids for r in orders):
                raise ValueError("Work orders do not belong to the requested incidents")
        roots = self.query("""
 SELECT DISTINCT f.id,f.source_record_id FROM fault_event f
 WHERE f.dataset_id=:dataset_id AND f.station_id=ANY(CAST(:stations AS uuid[]))
 AND (:no_incidents OR f.id=ANY(CAST(:incidents AS uuid[])))
 AND (:no_orders OR f.id IN(SELECT fault_id FROM maintenance_work_order
       WHERE dataset_id=:dataset_id AND id=ANY(CAST(:orders AS uuid[]))))
 AND (f.id=ANY(CAST(:incidents AS uuid[]))
   OR f.id IN(SELECT fault_id FROM maintenance_work_order
       WHERE dataset_id=:dataset_id AND id=ANY(CAST(:orders AS uuid[])))
   OR f.source_record_id=ANY(CAST(:sources AS uuid[]))
   OR f.station_event_id IN(SELECT id FROM station_event WHERE dataset_id=:dataset_id
                            AND source_record_id=ANY(CAST(:sources AS uuid[])))
   OR EXISTS(SELECT 1 FROM evidence_link l WHERE l.dataset_id=:dataset_id
     AND l.relationship='direct' AND ((l.from_record_id=f.source_record_id
       AND l.to_record_id=ANY(CAST(:sources AS uuid[]))) OR (l.to_record_id=f.source_record_id
       AND l.from_record_id=ANY(CAST(:sources AS uuid[]))))))
 ORDER BY f.id LIMIT 101
""")
        if len(roots) > 100:
            raise ValueError("Too many incident roots; narrow source identifiers")
        root_ids = [r["id"] for r in roots]
        root_sources = [r["source_record_id"] for r in roots]
        self.params["root_incidents"] = root_ids
        self.params["root_sources"] = root_sources
        sampled = (
            self.request.source_record_ids
            if self.params["no_incidents"] and self.params["no_orders"]
            else []
        )
        self.params["seeds"] = list(set(root_sources + sampled))
        links = self.query("""
 SELECT l.* FROM evidence_link l
 JOIN source_record a ON a.id=l.from_record_id AND a.dataset_id=:dataset_id
 JOIN source_record b ON b.id=l.to_record_id AND b.dataset_id=:dataset_id
 WHERE l.dataset_id=:dataset_id AND
   (l.from_record_id=ANY(CAST(:seeds AS uuid[])) OR l.to_record_id=ANY(CAST(:seeds AS uuid[])))
 ORDER BY l.relationship,l.id LIMIT 1001
""")
        if len(links) > 1000:
            raise ValueError("Too many linked records; narrow exact identifiers")
        related = set(self.params["seeds"])
        for link in links:
            related.update([link["from_record_id"], link["to_record_id"]])
        self.params["related"] = list(related)
        return root_ids, links

    def exact(self) -> list[dict]:
        return self.query(
            "WITH "
            + RECORDS
            + """
 SELECT r.*,0::float AS retrieval_score FROM records r
 WHERE r.id=ANY(CAST(:related AS uuid[]))
    OR r.incident_id=ANY(CAST(:root_incidents AS uuid[]))
    OR r.work_order_id=ANY(CAST(:orders AS uuid[]))
 ORDER BY CASE WHEN r.work_order_id=ANY(CAST(:orders AS uuid[])) THEN 0
               WHEN r.source_type='maintenance_work_order' THEN 1
               WHEN r.source_type='fault_event' THEN 2 ELSE 3 END,r.recorded_at,r.id
 LIMIT :limit
"""
        )

    def lexical(self) -> list[dict]:
        return self.query(
            "WITH "
            + RECORDS
            + """
 SELECT r.*,
   ts_rank_cd(r.search_vector,websearch_to_tsquery('english',:query))::float AS retrieval_score
 FROM records r WHERE r.search_vector @@ websearch_to_tsquery('english',:query)
 ORDER BY retrieval_score DESC,r.recorded_at,r.id LIMIT :limit
"""
        )

    def vector_count(self, spec: EmbeddingSpec) -> int:
        self.params["model_identity"] = spec.identity
        self.params["dimensions"] = spec.dimensions
        return self.query(
            "WITH "
            + RECORDS
            + """
 SELECT count(*) AS count FROM records
 WHERE embedding_model=:model_identity AND vector_dims(embedding)=:dimensions
"""
        )[0]["count"]

    def semantic(self, vector: list[float], spec: EmbeddingSpec) -> list[dict]:
        self.params.update(
            {
                "vector": str(validate_vector(vector, spec)),
                "model_identity": spec.identity,
                "dimensions": spec.dimensions,
                "distance": self.request.maximum_cosine_distance,
            }
        )
        # CASE prevents the planner from evaluating a distance on incompatible
        # dimensions before WHERE filtering; it is not safe to rely on clause order.
        return self.query(
            "WITH "
            + RECORDS
            + """,
 distances AS MATERIALIZED (
  SELECT r.*,CASE WHEN embedding_model=:model_identity AND vector_dims(embedding)=:dimensions
    THEN embedding <=> CAST(:vector AS vector) ELSE NULL END AS distance
  FROM records r
 )
 SELECT *,1-distance AS retrieval_score FROM distances
 WHERE distance<=:distance ORDER BY distance,recorded_at,id LIMIT :limit
"""
        )

    def relationships(self, ids: list[UUID]) -> list[dict]:
        self.params["returned_ids"] = ids
        return self.query("""
 SELECT l.* FROM evidence_link l
 JOIN source_record a ON a.id=l.from_record_id AND a.dataset_id=:dataset_id
 JOIN source_record b ON b.id=l.to_record_id AND b.dataset_id=:dataset_id
 WHERE l.dataset_id=:dataset_id AND
   (l.from_record_id=ANY(CAST(:returned_ids AS uuid[]))
    OR l.to_record_id=ANY(CAST(:returned_ids AS uuid[])))
 ORDER BY l.relationship,l.id LIMIT 1001
""")

    def source_identity(self, ids: list[UUID]) -> set[UUID]:
        return set(
            self.connection.scalars(
                select(SourceRecord.id).where(
                    SourceRecord.dataset_id == self.dataset["id"], SourceRecord.id.in_(ids)
                )
            )
        )
