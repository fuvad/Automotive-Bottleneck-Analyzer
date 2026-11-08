# Automotive Bottleneck Analyzer

Project foundation for an AI-assisted investigation of bottlenecks in a seven-station automotive body shop. The mixed line makes SUVs and sedans across two shifts. The exercise asks why a line designed for 60 jobs per hour has recently averaged about 46, whether the constraint changes, what causes losses, and how a 30% reduction in robot-fault downtime affects throughput.

See [the implementation plan](docs/implementation-plan.md) for the two-day MVP schedule and [AGENTS.md](AGENTS.md) for engineering conventions.

## Four-agent design

1. Orchestrator / Planner: interprets questions, validates scope, routes work, and composes the answer.
2. Data and Analytics Agent: computes historical metrics and ranks constraint candidates.
3. Knowledge and Root-Cause Agent: retrieves and interprets linked notes, work orders, Andon remarks, and SOPs.
4. Simulation Agent: runs SimPy baseline and what-if scenarios and reports line-level effects.

LangGraph will coordinate these four roles with validated routing. Numerical analytics and validation remain deterministic application code.

## Technology

Python 3.12+, Poetry, FastAPI, PostgreSQL, pgvector, SQLAlchemy 2.x, Alembic, Pydantic, SimPy, LangGraph, LangSmith, pytest, and Ruff. LLM and embedding providers are configurable. PostgreSQL stores structured records, document text/metadata, embeddings, evidence links, and audit records. Synthetic data, simulation and deterministic historical analytics are implemented; retrieval, agents and the business interface follow in later stages.

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

Copy `.env.example` to `.env`, then set `DATABASE_URL` to a PostgreSQL URL using the psycopg 3 driver. Configure model, embedding, and LangSmith keys before those features are implemented. The initialization milestone does not need a live PostgreSQL server for import and configuration checks.

```powershell
poetry install
poetry run uvicorn bottleneck_analyzer.main:app --reload
```

FastAPI exposes `/health`, `/health/database`, and its documentation interface.
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
persisted simulation results. The final suite passed 89 tests. Stages 1–4 and
Stage 2 final acceptance are complete; Stage 5 is ready and has not been started.
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
