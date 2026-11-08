# Stage 5 knowledge retrieval and evidence linking

## Architecture and public interfaces

Stage 5 adds deterministic evidence retrieval and qualified assessments. It does
not implement an agent, LangGraph, an LLM investigation loop, business endpoints,
UI, simulation behavior or a parallel analytics calculation. The four-agent
architecture and original two-day schedule remain unchanged (Day 1 hours 4.5–5.5).

```python
from bottleneck_analyzer.retrieval.service import retrieve, request_from_analytics

request, contexts = request_from_analytics(
    analytics_result, stations=["Hemming"], query="robot repair", limit=20
)
result = retrieve(engine, request, contexts=contexts)
```

`retrieve()` owns a PostgreSQL repeatable-read, read-only transaction. The
SELECT-only `retrieve_connection()` accepts a caller-owned connection, including
the existing rollback-only integration fixture. Optional method failures are
contained by savepoints. Retrieval performs no embedding writes or commits.

| Module in `src/bottleneck_analyzer/retrieval/` | Responsibility |
| --- | --- |
| `contracts.py` | Request, source evidence, relationship, candidate context, diagnostics and assessments |
| `repository.py` | Fixed parameterized dataset-scoped exact, full-text and pgvector queries |
| `chunking.py` | Whole records/sections and deterministic virtual fallback spans |
| `embeddings.py` | Optional real HTTP adapter, model identity, vector validation and source pooling |
| `indexing.py` | Explicit caller-owned enrichment of null embedding fields only |
| `evidence.py` | Identity deduplication, priority/rank fusion and conservative labels |
| `service.py` | Exact-first pipeline and one-way adapter from Stage 4 results |
| `cli.py` | Read-only terminal retrieval and optional JSON report |

The existing SQLAlchemy models, station vocabulary, relationship enum,
configuration, engine factory, generated full-text search column/index and
nullable pgvector fields are reused. No migration or dependency was added.
Alembic remains at `0002`.

## Request boundaries

`RetrievalRequest` requires one named dataset, candidate station names/UUIDs and
aware start/end timestamps. Periods are half-open `[start,end)` and must be inside
the dataset. Optional fault/work-order/source UUIDs are validated against that
same dataset and selected stations. Unknown/foreign identifiers fail explicitly;
there is no fallback to another dataset. Combined work-order/incident filters must
agree. Source samples cannot broaden an explicit incident/work-order restriction.

Source systems, UTC hours, shift name/dated UUID, query text, method controls,
result limit and maximum cosine distance are validated. Operational records use
their original recorded timestamp for filtering, so delayed maintenance outside
the requested period is intentionally not returned. UTC/shift filters apply to
that timestamp, not an assumed incident occurrence time. SOPs instead use
`effective_at < end`: they are procedural references, not events in that period.
Distinct effective versions remain distinct; the service does not silently choose
one as the latest approved procedure.

All dataset/station/time/system/incident predicates are enforced in SQL. Query
text is bound into `websearch_to_tsquery`, never interpolated as SQL. Retrieved
text cannot change queries, configuration, tools or application instructions.

The simulation datasets reference SOPs owned by `stage2-30day-v1`. A baseline
request does not return those records automatically. Diagnostics disclose the
reference; a caller must issue an explicit request for the SOP-owning dataset.
This preserves the Stage 5 prohibition on cross-dataset record disclosure.

## Exact, lexical and semantic retrieval

1. Resolve explicit incident/work-order identifiers and bounded Stage 4 source
   samples through fault/state/work-order FKs and direct source relationships.
2. Follow existing evidence links without converting inferred edges to direct
   ones. FK-linked child records work even if an evidence-link row is absent.
3. Retrieve exact source/incident/work-order records before broader searches.
4. Search the existing English generated `source_record.search_vector` with
   PostgreSQL `websearch_to_tsquery` and `ts_rank_cd`. The existing GIN index and
   source station/time indexes are retained unchanged.
5. If configured and compatible stored vectors exist in the same SQL-filtered
   scope, embed the query and use pgvector cosine distance (`<=>`). A CASE guard
   prevents evaluation on an incompatible dimension even if the planner reorders
   WHERE predicates. Identity and dimension must both match. Default maximum
   cosine distance is 0.5, selected from the live calibration/held-out checks
   below. This is a configurable synthetic-corpus cutoff, not an accuracy guarantee.
6. Merge by stable source/span identity. Direct exact hits precede inferred exact
   hits, which precede broader results. Within those bands, reciprocal rank fusion
   sums `1 / (60 + method_rank)`. Raw lexical/similarity scores are retained
   separately. A semantic hit cannot displace a direct exact hit by score alone.

Short text remains whole. SOP section sources retain their original identity,
document/version/effective date/sequence. Parent documents with usable sections
are excluded from search and enrichment to avoid duplicate content. A document
without usable sections has deterministic paragraph-aware spans of at most 2,000
characters, identified by UUIDv5(source UUID, policy/start/end). At most three
fallback spans per source are returned. They never create new source/section rows.

Fallback search scores describe the source document, not an independently indexed
span. Optional document vectors are normalized means of valid embeddings of its
fallback chunks. Sections and short records use one generated vector each. The
`source-v1` identity suffix records that representation policy. Arbitrarily large
sections are not silently truncated for embedding: the adapter rejects inputs
over its declared limit, leaving stored values untouched.

## Provenance and relationship semantics

`Evidence` retains the dataset UUID/name/provenance, source UUID/system/original
ID/path/timestamp, station, applicable incident/work-order metadata, original raw
fields, document version and section details. `original_text` preserves source
text separately from the displayed passage. `text_basis` explicitly distinguishes
original source text, SOP content and a rendering of normalized record fields
(for example a historian row with no source text). Derived renderings are not
presented as original quotations.

Every item records matching methods, method ranks/raw scores, direct/inferred
classification and basis. Original graph-edge directions, labels and bases remain
in `links`, including inferred edges alongside a distinct direct relationship.
Identical text from different incidents, documents or versions is not deduplicated.

A direct FK identifies a recorded incident relationship, not causation of line
loss. A station/time/search match is inferred. SOP relevance is always procedural
context rather than an incident match. Original physical repair fields can remain
in raw metadata; retrieval never uses them to replace scheduled fault-state time.

## Linking to analytics and assessment rules

`request_from_analytics()` consumes an existing validated Stage 4 result or selected
segment. It copies only candidate indicators/support/conflicts, aggregate IDs,
station/period/model metadata and bounded source samples. It does not rerun or
recalculate analytics and does not require loading a saved Stage 4 report. The
Stage 4 package has no dependency on retrieval. A supplied candidate context must
match the retrieval dataset, station and period. Model context is qualified:
retrieved shared station evidence has no exclusive SUV/Sedan attribution.

The deterministic assessment uses four labels:

- `recorded_maintenance_cause`: a maintenance row explicitly supplies
  `recorded_cause`; preserve the original wording and source. This is a reported
  cause, not proof of line-level causal loss.
- `observed_association`: usable records relate to the requested scope/incident
  without enough corroboration for an explanation. A shift note alone stays here.
- `supported_hypothesis`: direct fault and maintenance records from at least two
  source systems share an incident, and supplied Stage 4 fault occupancy is
  positive. The only automatic hypothesis is that equipment interruptions may
  contribute to observed station fault occupancy. No component cause, throughput
  attribution or recoverable gain is invented.
- `insufficient_evidence`: evidence is absent, procedural only, invalid,
  instruction-like, contradictory without usable support, or otherwise inadequate.

Bad/missing historian values are retained but excluded as measurements. Explicit
negative accounts and suspicious instruction-like text are visible as conflicting
evidence, not followed as instructions. Detection is a small heuristic, not a
complete prompt-injection detector; all content is always marked untrusted and no
execution facility exists. Candidate conflicts, exclusions and uncertainty remain
visible. Stage 4 metrics and separate Stage 3 simulation evidence remain authoritative.

## Embedding configuration and enrichment

The optional adapter follows the [official OpenAI embeddings API](https://developers.openai.com/api/docs/guides/embeddings).
The documented setup is:

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_API_KEY=<local secret>
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_TIMEOUT_SECONDS=10
```

The user configured the local `.env`; credentials were not printed or committed.
The configured model is now verified live. The client uses standard
library HTTPS, bounded requests/timeouts and explicit response model/index/count,
dimension, finite-value and nonzero-vector validation. Diagnostics never expose
provider response bodies, keys or connection strings. There is no API call at startup.

Stored `embedding_model` is the full provider:model:dimensions:source-v1 identity.
Vectors from another model/dimension are excluded. The optional
`index_sources(connection, dataset_uuid, source_uuids, embedder)` requires explicit
source selection (1–50) and a caller-owned transaction; it never commits. Only
previously null embedding/model pairs may be enriched. Compatible rows are skipped
without another API call; incompatible or partial metadata is rejected. All
generation/validation precedes writes; a savepoint makes updates atomic. Original
fields, sources, links, timestamps, dataset configuration and hashes are untouched.

Initial implementation verification used isolated rollback-only schemas. The user
subsequently authorized live enrichment: 2,544 eligible records now have compatible
vectors across the three existing datasets. Only the two derived embedding fields
changed; source facts, identifiers, links, calendars, production history, dataset
hashes and saved simulation reports remain unchanged. There is no implicit
backfill in retrieval/startup; `scripts/stage5_acceptance.py index` is an explicit
operator command.

Indexing batches unique texts (up to 64 inputs per provider request). An
operation-local `CachedEmbedder` reuses validated real vectors for identical text
under one model identity, including compatible pre-existing short-source vectors.
The 2,524 newly enriched rows required 22 new texts in 7 provider requests; the
user's existing 20 vectors were skipped. Dataset replay verification still checks
all source facts but excludes these two derived fields; a regression test confirms
that changing original text is still rejected after enrichment.

When configuration, vectors or the provider are unavailable, exact/full-text
retrieval still runs. Diagnostics name unavailable methods; semantic success is
never fabricated. Offline HTTP/geometry fixtures still test failure and compatibility
behavior without relying on paid calls. Live API, stored-vector retrieval and
synthetic-corpus relevance have now also been verified as described below.

## Diagnostics, limits and commands

The request limit is 1–100 (default 20); each method fetches at most three times
that limit. At most 100 incident roots and 1,000 graph links are expanded. SQL
returns bounded records, not the complete source corpus. No query runs per result
record. Diagnostics expose methods run/unavailable, bounded method hit counts,
duplicates merged, unique/returned counts, truncation, filters and warnings.
Match counts are fetched counts, not unbounded corpus totals.

```powershell
poetry run python -m bottleneck_analyzer.retrieval.cli --dataset sim-30day-baseline-v1 --station Hemming --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z --query "robot repair"
poetry run python -m bottleneck_analyzer.retrieval.cli --dataset stage2-30day-v1 --station Hemming --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z --query "alarm" --report data/processed/stage5/sop-example.json
```

Use `--incident <uuid>` or `--work-order <uuid>` for exact lookup. Report creation
refuses to overwrite an existing path. If Poetry is not on PATH, use the existing
`.\.venv\Scripts\python.exe -m ...`. Reports remain ignored local artifacts.

The initial pre-enrichment analytics-to-retrieval check preserved 46.88 JPH and Hemming.
Retrieval took **1.936 seconds**, issuing **16 SQL statements including savepoint
control**, during another validation run. It fetched 6 exact and 60 lexical hits,
returned 20 bounded records, and explicitly reported semantic search unavailable.
The output had Andon/CMMS/SCADA/historian evidence and a qualified generic
`supported_hypothesis`; no recorded component cause was fabricated. Its report
was 43,680 bytes before the final original-text provenance fields were added.
These are observations, not performance guarantees.

## Live semantic acceptance

The following scope was explicitly indexed; irrelevant stationless handover notes,
empty MES/SCADA/historian text and sectioned SOP parent documents were not embedded.
Structured historian evidence remains available through exact relationships.

| Dataset | Eligible / populated vectors | Newly populated |
| --- | ---: | ---: |
| `sim-30day-baseline-v1` | 1,644 | 1,624 (20 existed) |
| `sim-framing-validation-v1` | 147 | 147 |
| `stage2-30day-v1` | 753, including 14 SOP sections | 753 |
| Total | **2,544** | **2,524** |

Each dataset covers all seven stations. Every populated vector has 1,536 dimensions
and identity `openai:text-embedding-3-small:1536:source-v1`. A live 50-record replay
returned `indexed: 0, skipped: 50` with zero provider requests.

Eight labeled calibration probes measured nearest similarities. Relevant repair
queries scored 0.5363–0.6472; electrical repair scored 0.5889; approval guidance
scored 0.5982. Unrelated food/travel probes scored only 0.0473/0.0060. The previous
distance cutoff 0.4 (similarity ≥0.6) excluded valid broad/electrical/approval matches.
A maximum distance of **0.5** (similarity ≥0.5) accepts these examples while retaining
a substantial margin from the measured irrelevant probes. Probe mode uses cutoff
2 only to measure candidates; ordinary retrieval uses the stricter default.

The separate held-out fixture `tests/fixtures/live-retrieval-quality.json`, plus
station/boundary/hybrid checks, passed **17/17** live cases at the new default:

- Robot paraphrase: similarity **0.6428**, robot-fault records returned.
- Electrical paraphrase: **0.5399**, electrical-fault records returned.
- SOP reporting: **0.7307**, expected section 1/version retained.
- SOP approval: **0.5804**, expected section 2/version retained.
- Two held-out irrelevant recipe/currency queries: **zero returned hits**.
- Robot evidence scoped correctly to every baseline station and the Framing dataset.
- Original user's broad repair query: **0.5363**, now returns relevant records.
- Hybrid retrieval preserves direct-exact priority and one item per source/span,
  retaining exact/lexical/semantic match methods.
- End-exclusive timestamp and foreign-dataset identifier checks pass.

All live cases together used 2 provider requests via the local cache and took
21.19 seconds. This is a small, explicitly synthetic acceptance set, not a general
retrieval-quality benchmark or plant-causation validation. Repeated text belongs
to distinct incidents and remains distinct evidence. Text relevance does not
establish why line throughput was lost.

Reproduction (from the project root, with network/API access):

```powershell
poetry run python scripts/stage5_acceptance.py index --report data/processed/stage5/new-index-report.json
poetry run python scripts/stage5_acceptance.py probe --cutoff 2 --report data/processed/stage5/new-calibration-report.json
poetry run python scripts/stage5_acceptance.py validate --report data/processed/stage5/new-validation-report.json
```

Reports refuse overwrite. Indexing commits batches of at most 50 selected source
rows and is resumable; it does not create or regenerate datasets. `probe` and
`validate` are read-only. The runner audits all 21 business tables excluding only
the two authorized derived fields and compares saved Stage 3 report SHA-256 values.
Completed artifacts are `live-index-v2.json` (and its before audit),
`live-calibration-v1.json`, and `live-validation-v1.json` under ignored
`data/processed/stage5/`. The failed sandboxed attempt did not commit its first batch.

## Validation and remaining limits

Unit tests cover request/time validation, whole/section/fallback chunks, stable
identifiers, vector validation/model identity, HTTP response/error behavior,
deduplication/priority, all four labels, contradictions, malicious text and bad
historian data. PostgreSQL tests exercise FTS, exact FKs/graph edges, time and
station/dataset filtering, compatible/incompatible pgvector comparisons, provider
failure, enrichment atomicity/replay, SOP version metadata, fallback documents,
traceability and the Stage 4 adapter. Existing migrations run in isolated schemas.

Actual final counts/checks are recorded in [implementation status](../implementation-status.md).
Read-only preservation audits compare row counts and content digests for all 21
public business tables plus saved Stage 3 report SHA-256 values before/after final
verification. Live quality evidence is the bounded set above; no separate type checker is configured.

Limits: inference/classification is deliberately conservative and heuristic;
shared station evidence lacks model-exclusive attribution; sensor simulation is
not a physical causal model; old SOP versions are not automatically superseded;
embedding input and result expansion are bounded; graph traversal is one hop;
fallback scores are source-level; and relevance outside the acceptance examples
still needs evaluation. Stage 6
must consume these facts and limitations rather than turn them into causal certainty.
