# Stage 2 data model and operating instructions

## Scope and reuse

This stage reuses `core/config.py`, `db/base.py`, `db/session.py`, and the existing
Alembic environment. No dependency was added. PostgreSQL/pgvector, credentials,
the four-agent architecture, and the original two-day schedule are preserved.

The initial database inspection found no tables or migration revisions. The
target was confirmed as `bottleneck_analyzer`, role `bottleneck_app`, with
pgvector 0.8.7 already enabled. Revision `0001` creates only business tables and
indexes. It neither creates nor replaces the vector extension. It was reviewed
before application. No downgrade was executed.

## Entities and relationships

Every entity has a UUID primary key. Dataset-owned entities also have an indexed,
required `dataset_id` foreign key. UUIDv5 identities derive from the dataset name,
entity type, and source key. Another name creates independent data without deletion.

| Table | Relationships and important fields |
| --- | --- |
| `dataset` | Unique name, seed, UTC period, immutable configuration, content hash, provenance |
| `station` | Dataset, unique sequence 1–7/name, positive planned cycle in seconds |
| `buffer` | Upstream/downstream station FKs, unique upstream station per dataset, positive capacity |
| `vehicle_model` | Dataset, unique SUV/Sedan name |
| `shift` | Dataset, shift_1/shift_2, dated start/end, calendar timezone |
| `calendar_exclusion` | Shift FK, positive interval, reason; excluded planned breaks only |
| `vehicle` | Model FK, unique positive release sequence, release timestamp |
| `source_record` | Dataset, optional station FK, unique source system/ID, timestamp, raw JSONB, original export path, text, generated search vector, nullable vector/model |
| `production_record` | Vehicle/station/shift/source FKs, start/completion; one visit per vehicle/station for this MVP |
| `station_event` | Station/shift/source FKs, state and positive interval, computed duration |
| `fault_event` | Station/source/unique faulted-state FKs, category, equipment/code, interval and computed duration |
| `maintenance_work_order` | Station/source FKs, optional explicit fault FK, opened/closed, original description, status, optional recorded cause |
| `andon_event` | Station/source FKs, optional explicit fault FK, timestamp, original remarks |
| `shift_handover_note` | Shift/source FKs, optional station/fault FKs, timestamp, original text |
| `historian_observation` | Station/source FKs, optional fault FK, timestamp, measurement, value, unit and good/bad/missing quality |
| `sop_document` | Station/source FKs, unique title/version per dataset, category, effective date, full original content |
| `sop_section` | Document/source FKs, section sequence/title/content; unique sequence within document |
| `evidence_link` | Two source-record FKs, direct/inferred relationship and required basis; unique source pair |
| `model_configuration` | Dataset, version, parameters, optional approval identity/time; schema only |
| `simulation_run` | Configuration/dataset FKs, seed, parameters/results/time; schema only |
| `investigation_audit` | Dataset, question/route/state/time/final answer; schema only |

Models live in `db/models/production.py`. Manufacturing enums and fixture
configuration live in `domain/manufacturing.py`. Existing Stage 1 contracts stay
in their original modules. The final three tables have no generated rows or
runtime behavior in this stage; they satisfy the plan's durable-storage contract.

All timestamp columns use PostgreSQL `timestamptz`. Generator inputs must use
midnight UTC and all authored records use UTC. Database clients may display their
own timezone without changing the instant. Durations are computed from end minus
start, not independently sampled or summed. Foreign keys, required columns,
unique identities, positive intervals, allowed states/categories, sensor quality,
and positive buffer/cycle values have database constraints. Dataset validation
also checks the cross-record rules: same dataset, station ordering, buffer
adjacency, source references, state coverage, periods, and vehicle route ordering.

Exact incident links use real foreign keys. A station/time-only note leaves its
`fault_id` null and uses an `inferred` evidence link with an explanation. Missing
human records, unrelated notes, open/delayed work orders, unknown fault links,
and invalid sensor observations are retained rather than silently normalized away.

## Search preparation

`source_record.search_vector` is a stored PostgreSQL generated `tsvector` with a
GIN index, covering retained maintenance, Andon, note and SOP text. Station/time
and incident indexes support later precise lookup. The nullable pgvector column
has no fixed dimension until the embedding provider is selected. Embeddings and
embedding model names are left null. No retrieval or embedding pipeline runs here.

## Shared history and the Stage 3 dependency

The primary plan requires the final synthetic history to come from SimPy. This
request explicitly excludes simulation implementation. The current generator
therefore labels every dataset as `authored_fixture`, including the manifest and
validation report. It provides deterministic event fixtures and source projections
to verify the schema and ingestion pipeline. It does not claim fault propagation,
finite-buffer behavior, calibrated throughput, a confirmed constraint, or scenario
gains. Stage 3 must produce the simulation-derived replacement as a fresh dataset.

The default fixture uses 30 days from 2026-09-01 00:00 UTC, two eight-hour shifts
per day at 00:00 and 08:00, a 30-minute break in each shift, and 345 vehicles per
shift. Its volume reference is 345 / 7.5 = 46 JPH by construction, not a calibrated
simulation result. Design capacity remains the separate 60 JPH setting. These are
synthetic calendar choices, not descriptions of a real plant's schedule.

`tests/fixtures/framing_history.json` supplies higher *authored fault duration* at
Framing and tests that the records reflect that input. Simulation sensitivity must
still establish whether Framing is the stronger line constraint. That cross-stage
acceptance is now complete: Stage 3 verified the Framing stress case and loaded/
replayed `sim-30day-baseline-v1`, preserving this authored fixture unchanged.
See [the Stage 3 technical document](stage-3-simulation.md) for the measured
results and the separate `sim-framing-validation-v1` dataset. Stage 3 consumed
the completed schema and authored-data pipeline before supplying the remaining
acceptance evidence; there was no circular implementation dependency.

## Generate, validate, and load

Run all commands from the project root with the existing `.env`:

```powershell
poetry run alembic current
poetry run alembic upgrade head
poetry run python -m bottleneck_analyzer.data.generators.cli --validate-only
poetry run python -m bottleneck_analyzer.data.generators.cli
```

The last command creates `data/raw/stage2-30day-v1/` with MES/historian CSV,
SCADA/CMMS/Andon/shift-note/SOP JSONL, seven original SOP text files, and a
manifest. Read-only file and database connectors live in `data/connectors/mock.py`.
The source record stores the original file reference and original fields beside
normalized rows. These local source artifacts are ignored by Git.

The loader uses the existing SQLAlchemy engine and a single transaction. It
validates before insertion and compares stored values and counts before reporting
success. An advisory transaction lock protects concurrent generation of the same
identity. Rerunning the same command returns `created: false` after verification;
changed content under an existing name is rejected. Exports also reject an
existing conflicting directory. A new dataset needs a new name:

```powershell
poetry run python -m bottleneck_analyzer.data.generators.cli --name trial-seed-73 --seed 73 --days 2 --vehicles-per-shift 12
```

No cleanup command deletes datasets. Failed database transactions roll back.
Configuration supports 1–366 days and 2–400 vehicles per shift. The upper volume
bound keeps the authored single-station booking slots nonoverlapping; simulation
release behavior will be defined in Stage 3.

Stage 5 subsequently enriches only `source_record.embedding` and
`source_record.embedding_model`. Replay verification excludes these derived fields
while strictly comparing original text/JSON, identifiers, timestamps, relationships
and all other generated fields. The dataset hash remains the original generated
history fingerprint, not a checksum of a later embedding cache. Enrichment replay
and original-source tamper rejection are covered by a dedicated integration test.

## Tests and database safety

```powershell
poetry run pytest tests/unit -q
$env:STAGE2_TEST_POSTGRES = '1'
poetry run pytest -q
Remove-Item Env:STAGE2_TEST_POSTGRES
poetry run ruff check .
poetry run alembic check
```

Business-schema integration tests require explicit opt-in. They create a unique
`stage2_test_<uuid>` schema within a transaction, apply the real migration there,
assert every business table exists in that schema, and use that schema first in
the local search path. The public vector extension is reused. The entire schema,
tables and test data disappear on rollback; cleanup never drops user tables. The
fixture verifies the temporary schema no longer exists. Public development data
is not modified by tests. The existing Stage 1 live test remains read-only.

This is the isolated-schema test strategy because the application role has no
CREATEDB privilege. To use a separate test database later, its owner must provision
it explicitly; this stage does not change database roles or credentials.

If Poetry is not on PATH, use the already-installed environment directly:
`.\.venv\Scripts\python.exe -m pytest`, `.\.venv\Scripts\ruff.exe check .`, and
`.\.venv\Scripts\python.exe -m alembic current`. No type checker is currently
configured; bytecode/import checks and pytest cover importability.
