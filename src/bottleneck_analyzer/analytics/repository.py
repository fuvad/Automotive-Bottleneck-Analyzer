"""Parameterized, dataset-scoped PostgreSQL aggregates. No writes or ORM results."""

import json
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from bottleneck_analyzer.analytics.calendar import Segment
from bottleneck_analyzer.db.models.production import (
    Buffer,
    CalendarExclusion,
    Dataset,
    Shift,
    SimulationRun,
    Station,
)

# At most a few thousand small calendar windows are sent to PostgreSQL. Large
# operation/state/source histories stay in PostgreSQL throughout aggregation.
WINDOWS = """
w AS MATERIALIZED (
 SELECT * FROM jsonb_to_recordset(CAST(:windows AS jsonb)) AS x(
   key text, a timestamptz, b timestamptz, scheduled boolean, model text)
)
"""
OPERATIONS = """
ops AS MATERIALIZED (
 SELECT p.*, v.released_at, m.name AS model,
        (s.raw->>'processing_seconds')::double precision AS service,
        (s.raw->>'waiting_wall_seconds')::double precision AS waiting,
        (s.raw->>'blocked_wall_seconds')::double precision AS blocking,
        :origin + (s.raw->>'arrival')::double precision * interval '1 second' AS arrival,
        s.source_id,
        s.raw->>'simulation' AS simulated
 FROM production_record p
 JOIN vehicle v ON v.id=p.vehicle_id AND v.dataset_id=:dataset_id
 JOIN vehicle_model m ON m.id=v.model_id AND m.dataset_id=:dataset_id
 JOIN source_record s ON s.id=p.source_record_id AND s.dataset_id=:dataset_id
 WHERE p.dataset_id=:dataset_id
)
"""


class AnalyticsRepository:
    def __init__(self, connection: Connection, dataset_name: str):
        self.connection = connection
        row = connection.execute(select(Dataset.__table__).where(Dataset.name == dataset_name))
        self.dataset = row.mappings().one_or_none()
        if self.dataset is None:
            raise ValueError(f"Requested dataset does not exist: {dataset_name}")
        self.dataset = dict(self.dataset)
        self.dataset_id = self.dataset["id"]
        self.shifts = sorted(self.small_rows(Shift), key=lambda s: (s["start_time"], str(s["id"])))
        self.exclusions = self.small_rows(CalendarExclusion)
        self.stations = sorted(self.small_rows(Station), key=lambda s: s["sequence"])
        self.buffers = self.small_rows(Buffer)
        self.runs = self.small_rows(SimulationRun)

    def small_rows(self, model: Any) -> list[dict]:
        return [
            dict(r)
            for r in self.connection.execute(
                select(model.__table__).where(model.dataset_id == self.dataset_id)
            ).mappings()
        ]

    def configure(self, segments: list[Segment]) -> None:
        windows = []
        for segment in segments:
            for scheduled, intervals in ((False, segment.windows), (True, segment.scheduled)):
                for a, b in intervals:
                    cursor = a
                    while cursor < b:
                        boundary = cursor.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
                        stop = min(b, boundary + timedelta(hours=1))
                        windows.append(
                            {
                                "key": segment.key,
                                "a": cursor.isoformat(),
                                "b": stop.isoformat(),
                                "scheduled": scheduled,
                                "model": segment.model,
                            }
                        )
                        cursor = stop
        self.params = {
            "dataset_id": self.dataset_id,
            "origin": self.dataset["start_time"],
            "horizon": self.dataset["end_time"],
            "windows": json.dumps(windows),
        }

    def query(self, sql: str) -> list[dict]:
        return [dict(r) for r in self.connection.execute(text(sql), self.params).mappings()]

    def operations(self) -> list[dict]:
        return self.query(
            "WITH "
            + WINDOWS
            + ","
            + OPERATIONS
            + """
 SELECT w.key, p.station_id, count(*) AS operations,
        avg(extract(epoch FROM p.completed_at-p.started_at)) AS elapsed,
        count(service) AS service_count, avg(service) AS service,
        avg(waiting) AS waiting, avg(blocking) AS blocking,
        min(p.source_record_id::text) AS source_record_id,
        min(p.source_id) AS example_source_id
 FROM w JOIN ops p ON date_trunc('hour',p.completed_at)=date_trunc('hour',w.a)
   AND p.completed_at >= w.a AND p.completed_at < w.b
   AND (w.model IS NULL OR p.model=w.model)
 WHERE NOT w.scheduled
 GROUP BY w.key, p.station_id
"""
        )

    def states(self) -> list[dict]:
        return self.query(
            "WITH "
            + WINDOWS
            + """,
 slices AS MATERIALIZED (
   SELECT e.*,h FROM station_event e
   CROSS JOIN LATERAL generate_series(date_trunc('hour',e.start_time),
      date_trunc('hour',e.end_time-interval '1 microsecond'),interval '1 hour') AS h
   WHERE e.dataset_id=:dataset_id
 ), clipped AS MATERIALIZED (
   SELECT w.key, e.station_id, e.state, e.source_record_id,
          greatest(e.start_time,w.a) AS a, least(e.end_time,w.b) AS b
   FROM w JOIN slices e ON e.h=date_trunc('hour',w.a)
     AND e.start_time < w.b AND e.end_time > w.a
   WHERE w.scheduled AND w.model IS NULL
 ), totals AS (
   SELECT key,station_id,state,count(DISTINCT source_record_id) AS count,
          sum(extract(epoch FROM b-a))::float AS seconds,
          min(source_record_id::text) AS sample
   FROM clipped GROUP BY key,station_id,state
 ), coverage AS (
   SELECT key,station_id,range_agg(tstzrange(a,b,'[)')) AS ranges,
          sum(extract(epoch FROM b-a))::float AS total
   FROM clipped GROUP BY key,station_id
 ), unions AS (
   SELECT key,station_id,total,
          (SELECT sum(extract(epoch FROM upper(r)-lower(r)))::float
           FROM unnest(ranges) AS r) AS covered
   FROM coverage
 )
 SELECT t.*,u.covered,greatest(0,u.total-u.covered) AS overlap
 FROM totals t JOIN unions u USING(key,station_id)
 ORDER BY key,station_id,state
"""
        )

    def line(self) -> list[dict]:
        return self.query(
            "WITH "
            + WINDOWS
            + """,
 bodies AS MATERIALIZED (
   SELECT v.id,v.released_at,m.name AS model,p.completed_at
   FROM vehicle v JOIN vehicle_model m ON m.id=v.model_id AND m.dataset_id=:dataset_id
   LEFT JOIN production_record p ON p.vehicle_id=v.id AND p.dataset_id=:dataset_id
      AND p.station_id=(SELECT id FROM station WHERE dataset_id=:dataset_id AND sequence=7)
   WHERE v.dataset_id=:dataset_id
 ), events AS (
   SELECT model,released_at AS t,1 AS admitted,0 AS completed,0::numeric AS flow FROM bodies
   UNION ALL
   SELECT model,completed_at,0,1,extract(epoch FROM completed_at-released_at)
   FROM bodies WHERE completed_at IS NOT NULL
 ), selected AS (
   SELECT w.key,b.model,
      sum(b.admitted)::int AS admitted,sum(b.completed)::int AS completed,sum(b.flow) AS flow
   FROM w JOIN events b ON date_trunc('hour',b.t)=date_trunc('hour',w.a)
      AND b.t>=w.a AND b.t<w.b AND (w.model IS NULL OR w.model=b.model)
   WHERE NOT w.scheduled GROUP BY w.key,b.model
 ), endpoints AS (
   SELECT key,model,min(a) AS a,max(b) AS b FROM w WHERE NOT scheduled GROUP BY key,model
 ), stocks AS (
   SELECT w.key,
      count(*) FILTER (WHERE b.released_at<w.a
                        AND (b.completed_at IS NULL OR b.completed_at>=w.a)) AS initial_wip,
      count(*) FILTER (WHERE b.released_at<w.b
                        AND (b.completed_at IS NULL OR b.completed_at>=w.b)) AS final_wip
   FROM endpoints w LEFT JOIN bodies b ON w.model IS NULL OR w.model=b.model GROUP BY w.key
 )
 SELECT t.key,s.model,coalesce(s.admitted,0) AS admitted,
        coalesce(s.completed,0) AS completed,coalesce(s.flow,0) AS flow,
        t.initial_wip,t.final_wip FROM stocks t LEFT JOIN selected s USING(key)
"""
        )

    def queue_tail(self) -> list[dict]:
        """Only bounded censored WIP is read into Python, never full vehicle history."""
        origin, horizon = self.dataset["start_time"], self.dataset["end_time"]
        rows = []
        for run in self.runs:
            for vehicle in run["results"].get("censored_vehicles", []):
                operations = vehicle["operations"]
                # Completed operations already exist in MES. An unfinished operation
                # still supplies its queue wait; a not-yet-started visit ends at horizon.
                for op in operations:
                    if op["end"] is None:
                        rows.append(
                            {
                                "station": op["station"],
                                "model": vehicle["model"],
                                "a": origin + timedelta(seconds=op["arrival"]),
                                "b": origin + timedelta(seconds=op["start"]),
                            }
                        )
                if not operations or operations[-1]["departure"] is not None:
                    index = operations[-1]["station"] + 1 if operations else 0
                    if index < 7:
                        rows.append(
                            {
                                "station": index,
                                "model": vehicle["model"],
                                "a": origin + timedelta(seconds=vehicle["arrival"]),
                                "b": horizon,
                            }
                        )
        return rows

    def occupancy(self, kind: str) -> list[dict]:
        """Sweep interval endpoints in SQL; integrate only selected scheduled time."""
        if kind == "queue":
            tail = [
                {**r, "a": r["a"].isoformat(), "b": r["b"].isoformat()} for r in self.queue_tail()
            ]
            self.params["tail"] = json.dumps(tail)
            intervals = (
                OPERATIONS
                + """,
            intervals AS (
              SELECT s.sequence AS station,p.model,p.arrival AS a,p.started_at AS b
              FROM ops p JOIN station s ON s.id=p.station_id AND s.dataset_id=:dataset_id
              WHERE p.simulated='true' AND p.arrival<p.started_at
              UNION ALL
              SELECT t.station+1,t.model,t.a,t.b
              FROM jsonb_to_recordset(CAST(:tail AS jsonb)) AS t(
                station int,model text,a timestamptz,b timestamptz) WHERE t.b>t.a
            )
            """
            )
        else:
            intervals = """intervals AS (
              SELECT 0 AS station,m.name AS model,v.released_at AS a,
                     coalesce(p.completed_at,:horizon) AS b
              FROM vehicle v
              JOIN vehicle_model m ON m.id=v.model_id AND m.dataset_id=:dataset_id
              LEFT JOIN production_record p ON p.vehicle_id=v.id AND p.dataset_id=:dataset_id
                AND p.station_id=(SELECT id FROM station
                                  WHERE dataset_id=:dataset_id AND sequence=7)
              WHERE v.dataset_id=:dataset_id
            )"""
        return self.query(
            "WITH "
            + WINDOWS
            + ","
            + intervals
            + """,
 versions AS (
   SELECT station,NULL::text AS model,a,b FROM intervals
   UNION ALL SELECT station,model,a,b FROM intervals
 ), deltas AS (
   SELECT station,model,a AS t,1 AS delta FROM versions
   UNION ALL SELECT station,model,b AS t,-1 AS delta FROM versions
 ), grouped AS (
   SELECT station,model,t,sum(delta) AS delta FROM deltas GROUP BY station,model,t
 ), sweep AS (
   SELECT station,model,t,lead(t) OVER q AS next_t,
          sum(delta) OVER (PARTITION BY station,model ORDER BY t) AS occupancy
   FROM grouped WINDOW q AS (PARTITION BY station,model ORDER BY t)
 ), slices AS MATERIALIZED (
   SELECT s.*,h FROM sweep s
   CROSS JOIN LATERAL generate_series(date_trunc('hour',s.t),
       date_trunc('hour',s.next_t-interval '1 microsecond'),interval '1 hour') AS h
   WHERE s.next_t>s.t
 )
 SELECT w.key,s.station,
   sum(extract(epoch FROM least(s.next_t,w.b)-greatest(s.t,w.a))*s.occupancy)::float AS area,
   max(s.occupancy) FILTER (WHERE s.next_t-s.t>interval '2 microseconds')::int AS maximum
 FROM w JOIN slices s ON s.h=date_trunc('hour',w.a)
   AND s.t<w.b AND s.next_t>w.a AND s.model IS NOT DISTINCT FROM w.model
 WHERE w.scheduled GROUP BY w.key,s.station
"""
        )
