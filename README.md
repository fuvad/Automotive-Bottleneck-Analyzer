# Automotive Bottleneck Analyzer

Project foundation for an AI-assisted investigation of bottlenecks in a seven-station automotive body shop. The mixed line makes SUVs and sedans across two shifts. The exercise asks why a line designed for 60 jobs per hour has recently averaged about 46, whether the constraint changes, what causes losses, and how a 30% reduction in robot-fault downtime affects throughput.

See [the implementation plan](docs/implementation-plan.md) for the two-day MVP schedule and [AGENTS.md](AGENTS.md) for engineering conventions.

## Four-agent design

1. Orchestrator / Planner: interprets questions, validates scope, routes work, and composes the answer.
2. Data and Analytics Agent: computes historical metrics and ranks constraint candidates.
3. Knowledge and Root-Cause Agent: retrieves and interprets linked notes, work orders, Andon remarks, and SOPs.
4. Simulation Agent: runs SimPy baseline and what-if scenarios and reports line-level effects.

LangGraph coordinates these four roles with validated routing. Numerical analytics and validation remain deterministic application code.

## Technology

Python 3.12+, Poetry, FastAPI, PostgreSQL, pgvector, SQLAlchemy 2.x, Alembic, Pydantic, SimPy, LangGraph, LangSmith, pytest, and Ruff. LLM and embedding providers are configurable. PostgreSQL stores structured records, document text/metadata, embeddings, evidence links, and audit records. Synthetic data, simulation, historical analytics, retrieval, four-agent orchestration, the API and local web interface are implemented.

## Project layout

| Path | Purpose |
| --- | --- |
| `src/bottleneck_analyzer/agents/` | Four agent implementations and contracts |
| `analytics/`, `retrieval/`, `simulation/` | Metrics, evidence retrieval, and discrete-event simulation |
| `data/connectors/`, `data/generators/` | Mock source interfaces and synthetic records |
| `db/`, `alembic/` | PostgreSQL mappings, sessions, and migrations |
| `domain/`, `workflows/`, `api/`, `core/` | Shared types, LangGraph routes, HTTP, and configuration |
| `tests/`, `data/`, `scripts/`, `docs/` | Tests, local datasets, scripts, and design material |

## Prerequisites and setup

Install Python 3.12 or newer, Poetry, PostgreSQL, and the matching PostgreSQL `pgvector` extension. Set up a local database and a role that can access it. Enable the extension in that database when installed:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

For a fresh installation, copy `.env.example` to `.env`, then set `DATABASE_URL` to a PostgreSQL URL using the psycopg 3 driver. Preserve an existing configured `.env` and database. Configure language/embedding providers for investigation execution; LangSmith remains optional. Liveness and the UI can start without PostgreSQL or provider access.

```powershell
poetry install
poetry run python -m bottleneck_analyzer.api.cli
```

Open `http://127.0.0.1:8000/`. The supported launcher uses one worker without reload,
requires loopback binding and disables proxy-header trust. FastAPI also exposes
`/health`, `/health/database`, and `/docs`. If Poetry is not on PATH, use
`.\.venv\Scripts\python.exe -m bottleneck_analyzer.api.cli`.
See [the Stage 2 data model and operating instructions](docs/design/stage-2-data-model.md)
for the business schema, synthetic fixture generator, exports, and isolated database tests.

## Database and migrations

Alembic loads `DATABASE_URL` through the existing application settings. Revision
`0001` adds 21 business tables, constraints, indexes, full-text preparation, and
nullable pgvector storage. Check and apply the reviewed migration with:

```powershell
poetry run alembic current
poetry run alembic upgrade head
```

The migration reuses the enabled vector extension. It does not reinstall it or
recreate the database. Generate a fixture explicitly after migrating:

```powershell
poetry run python -m bottleneck_analyzer.data.generators.cli
```

An identical rerun verifies the dataset without adding duplicate rows. Use a new
`--name` for a fresh dataset. This command produces authored fixtures. Stage 3
also provides the separate persisted simulation-derived baseline and Framing case;
analytics selects the dataset explicitly and preserves the authored fixture.

## Checks

```powershell
poetry check
poetry run pytest
poetry run ruff check .
```

Tests cover the foundation, manufacturing contracts, fixtures, source exports,
database constraints, and migration consistency. Stage 2 database-write tests are
opt-in using `STAGE2_TEST_POSTGRES=1` and run inside rollback-only isolated schemas.
The existing PostgreSQL health test uses read-only statements.

## Current status

Stage 1 foundation is verified. Stage 2 implementation is complete: domain/schema,
migration, and authored-data generation/loading are available for Stage 3 to use.
Stage 3 implements the seven-station SimPy line, finite buffers, faults/repairs,
calendars, uncertainty, calibration, scenarios and source projections. Its
30-day baseline and Framing validation datasets are generated and persisted.
Replay and original-fixture preservation checks passed. Stage 4 adds read-only
historical metrics, segmentation and qualified candidate ranking, verified against
persisted simulation results. Stage 5 adds bounded evidence retrieval, optional
compatible pgvector search, provenance and qualified assessments. Stage 6 connects
the four agents with LangGraph, validated routing and durable investigation audit.
Stages 1–7 and
Stage 2 final acceptance are complete; Stage 8 remains Not Started.
Live Stage 6 planning passed eight cases and the complete combined
investigation passed. Live semantic acceptance passed 17/17 checks,
using 2,544 indexed text records across the three existing datasets.
See [implementation status](docs/implementation-status.md) for actual validation
outcomes and the remaining acceptance evidence.

## Simulation commands

See [Stage 3 simulation](docs/design/stage-3-simulation.md) for assumptions,
actual experiment results, module responsibilities and all reproduction commands.

```powershell
poetry run python -m bottleneck_analyzer.simulation.cli baseline --days 1
poetry run python -m bottleneck_analyzer.simulation.cli replicate --days 3 --replications 5
```

Commands without `--config` use the initial synthetic assumptions. Use the saved
calibrated configuration for the evaluated 46-JPH baseline. Simulation never runs
on application startup. The authored `stage2-30day-v1` dataset is preserved.

## Historical analytics commands

Analytics reads PostgreSQL in a read-only snapshot; it does not run the simulation
or ingest raw exports. It calculates Final Inspection JPH, design gap, station
metrics, dated shifts, SUV/Sedan contributions, UTC-hour groups and qualified
historical candidates with source references.

```powershell
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-30day-baseline-v1
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-framing-validation-v1
poetry run python -m bottleneck_analyzer.analytics.cli --dataset sim-30day-baseline-v1 --model SUV --utc-hour 4
```

Use `--report data/processed/stage4/example.json` to create a local structured
report at a fresh path. Optional `--start`/`--end` must include timezone offsets.
The baseline's retained single run gives 46.88 JPH and ranks Hemming first;
this differs from the separate 20-replication mean of 46.255889 JPH. Model rankings
use qualified service/queue proxies because shared machine states lack model
attribution. Historical scores are not proof of a real-plant constraint.
See [Stage 4 analytics](docs/design/stage-4-analytics.md) for definitions, scoring,
filters, source references, limitations, experiment association and validation.

## Evidence retrieval commands

Retrieval uses exact incident/work-order links first, then PostgreSQL full-text
and optional pgvector search within the explicitly selected dataset and stations.
It retains direct/inferred links, source/version metadata, candidate indicators,
quality warnings and qualified evidence labels. Source text remains untrusted data.

```powershell
poetry run python -m bottleneck_analyzer.retrieval.cli --dataset sim-30day-baseline-v1 --station Hemming --start 2026-09-01T00:00:00Z --end 2026-10-01T00:00:00Z --query "robot repair"
```

Use `--incident <uuid>`, `--work-order <uuid>`, or an optional fresh `--report` path.
The Python `request_from_analytics()` adapter links the existing Stage 4 result
without recalculating metrics. Simulation SOPs belong to a separately referenced
authored dataset; retrieval never silently mixes them into baseline evidence.

Optional embedding settings include provider/model/key, dimensions, HTTPS base
URL and timeout. The supported OpenAI setup uses `text-embedding-3-small` with
1,536 dimensions. Missing configuration/vectors or provider failure leaves exact
and lexical retrieval available, with explicit partial-result diagnostics.
The user-authorized live enrichment populated 2,544 relevant records, including
14 SOP sections. Indexing never runs during retrieval or application startup.
The default cosine-distance cutoff is 0.5, validated on the documented synthetic
acceptance examples. An explicit, resumable indexing and validation utility is
available:

```powershell
poetry run python scripts/stage5_acceptance.py validate --report data/processed/stage5/new-validation.json
```

Use `index` instead of `validate` only when intentionally enriching newly eligible
records. Existing compatible vectors are skipped, and original source facts remain
strictly checked on dataset replay. Reports require fresh paths.
See [Stage 5 retrieval](docs/design/stage-5-retrieval.md) for interfaces, indexing,
configuration, safeguards, tests and remaining limits.

## Investigation workflow commands

Stage 6 connects the four agents through predefined historical, causes,
segmentation, simulation and combined routes. Configure `LLM_PROVIDER=openai`,
`LLM_MODEL` and `LLM_API_KEY` in the local `.env`. The model must support Responses
structured outputs. No provider key is included in Git. The configured model is
used as supplied; there is no automatic model substitution or fake fallback.

```powershell
poetry run python -m bottleneck_analyzer.workflows.cli --request tests/fixtures/stage6-combined-request.json --report data/processed/stage6/combined-example.json
```

The example uses existing historical data and 20 paired baseline/scenario
replications. It adds a durable investigation audit record; it does not overwrite
production history, generate a dataset, or index embeddings. Reports require fresh
paths. A simulation worker enforces a configurable runtime limit (600 seconds by
default). An ambiguous request to reduce robot-fault downtime asks whether to
reduce repair duration or failure rate. Human review is required before acting.

The Python entry point is
`workflows.graph.InvestigationWorkflow(engine).run(InvestigationRequest(...))`.
Use a separate workflow instance for each concurrent investigation. Follow-ups
can explicitly reuse a validated scope. Tracing is optional; PostgreSQL audit
records remain required. Historical figures, source evidence and modeled
predictions are separate response fields, with warnings, conflicts and uncertainty.
No new business HTTP endpoint or UI is included in Stage 6.

Explicit paid live acceptance (outside the ordinary regression suite):

```powershell
poetry run python scripts/stage6_acceptance.py planning --report data/processed/stage6/new-planning.json
poetry run python scripts/stage6_acceptance.py combined --report data/processed/stage6/new-combined.json
```

See [Stage 6 orchestration](docs/design/stage-6-orchestration.md) for contracts,
service boundaries, provider behavior, routing, audit, limits and validation.

## Local investigation interface and API

The local UI is a single conversation. Select the dataset and UTC period at the
top, select an example or type a question, then press **Send** (or Enter;
Shift+Enter inserts a newline). Ask about stations, models, shifts and either
intervention in your question. Ambiguous interventions request clarification.
Answers lead with the result relevant to your question in plain language.
Maintenance questions explain the evidence; what-if questions lead with the
estimated change and its uncertainty. Each answer has **View evidence**, including historical measurements and source
samples, retrieved passages, modeled uncertainty, and limitations.

Follow up naturally: “Why is that happening?” uses bounded summaries of the last
five finalized exchanges from this chat. Older messages remain visible but are
outside model context. Changing the dataset or period starts fresh context.
**New chat** clears the visible conversation and its context connection; durable
audit records remain. Refresh restores this one conversation from browser-local
identifiers and scope, fetching saved answers without repeating submissions.
There is no archived-chat browser. New chat and scope changes are disabled during
known active execution.

`POST /api/investigations` accepts the existing Stage 6 request and requires a UUID
`X-Submission-Key`. HTTP 202 follows initial audit commitment; poll the returned
status/result links. `GET /api/submissions/{key}` reconciles uncertain admission.
Dataset catalog/options and bounded investigation history are read-only GETs.
All five finalized Stage 6 outcomes are retrieved with HTTP 200; workflow outcome
is separate from API success. An unfinished audit is never presented as complete.

Only one API investigation runs at a time. There is no durable queue, automatic
resume or guaranteed deduplication across restart. Shutdown drains accepted work;
a full simulation can take several minutes. Refresh/reconnect performs GETs only.
Saved results are labeled as saved and can be viewed without a model call or
simulation rerun. The interface has no production controls or approval automation.

Initial Stage 7 acceptance used fixture model/browser journeys and read-only rendering of
the existing live combined audit. No production simulation, reseeding, embedding
indexing or paid provider call was repeated during Stage 7.
See [Stage 7 API/UI](docs/design/stage-7-api-ui.md) for endpoints, admission races,
security boundaries, limits and browser acceptance.

```powershell
$env:STAGE2_TEST_POSTGRES='1'
$env:STAGE7_TEST_SAVED_BROWSER='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
Remove-Item Env:STAGE7_TEST_SAVED_BROWSER
node --test tests/ui/client.test.mjs
```

Edge headless acceptance uses the existing installed browser; no browser package
was added. Missing Edge is an explicit skip, with manual acceptance instructions
documented separately. Generated acceptance reports remain ignored by Git.

The responsive chat keeps the composer visible. **View evidence** gives a short,
plain-language explanation with relevant figures or up to three source excerpts,
rather than a technical audit dump. Full records remain in the saved audit and
existing API result. Investigation IDs are copyable. Windows CSS MIME
handling remains `text/css`, preserving CSP and `nosniff`. Chat screenshots and
browser reports are under ignored `data/processed/stage7/chat/`. The pre-existing
favicon 404 remains because the user declined a favicon asset.
