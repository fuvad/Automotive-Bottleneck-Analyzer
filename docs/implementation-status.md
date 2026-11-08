# Implementation Status

## Project information

- **Project name:** Automotive Bottleneck Analyzer
- **Overall status:** In Progress
- **Current stage:** Stage 7 — API and Local User Interface (Completed; Stage 8 Not Started)
- **Stage 2:** Implementation and Final Acceptance Completed
- **Stage 3:** Completed
- **Last updated:** 2026-11-09
- **Source of truth:** [`implementation-plan.md`](implementation-plan.md) and [`implementation-roadmap.md`](implementation-roadmap.md)

## Stage status

| Stage | Implementation status | Final acceptance / notes |
| --- | --- | --- |
| Stage 1 — Project Foundation and Configuration | Completed | Foundation implementation, local checks, authenticated PostgreSQL connectivity, and pgvector operation verification completed. |
| Stage 2 — Domain Models, Database Schema, and Synthetic Data Generation | Completed | Final acceptance closed: 30-day simulation dataset loaded/replayed, Framing case verified, authored fixture unchanged. |
| Stage 3 — Seven-Station SimPy Discrete-Event Simulation | Completed | Simulation, calibration, uncertainty, both interventions, persistence/replay and final 64-test suite verified. |
| Stage 4 — Historical Analytics and Bottleneck Candidate Identification | Completed | Read-only metrics, segmentation, source references, candidates, persisted reference comparisons and final 89-test suite passed. |
| Stage 5 — Knowledge Retrieval and Evidence Linking | Completed | Live semantic acceptance closed: 2,544 vectors, 17/17 live checks, source-fact preservation and final 125-test suite passed. |
| Stage 6 — Four-Agent Implementation and LangGraph Orchestration | Completed | 192 tests; 20 final focused checks; 8 live planning/guard cases; complete live combined workflow and preservation audit passed. |
| Stage 7 — API and Local User Interface | Completed | Chat refinement verified: 244 pytest tests, six Node tests, four final Edge checks, real follow-up context and original-record preservation. |
| Stage 8 — Testing, Validation, Documentation, and Presentation | Not Started | Waiting for the implemented vertical workflow. |

## Completed tasks

- Read the project `AGENTS.md`, `docs/implementation-plan.md`, and `docs/implementation-roadmap.md` before implementation.
- Audited the existing package, dependency configuration, environment template, SQLAlchemy session, Alembic environment, and starter tests.
- Extended typed settings for application/runtime values, production-rate references, LLM/embedding providers, and LangSmith configuration.
- Added foundational contracts for analysis scope, evidence references, scenario requests, investigation state, question intent, status, and evidence relationships.
- Added PostgreSQL-only database health inspection, pgvector availability reporting, and a FastAPI database-session dependency.
- Added `/health` and `/health/database` endpoints with startup/shutdown logging and tracing-disabled operation.
- Added isolated foundation tests for settings, health endpoints, missing database configuration, and shared contract validation.

Stages 1–7 are complete. Stage 3's verified simulation datasets close Stage 2 final
acceptance. Stage 8 has not started. The execution records below
retain the earlier pending state and the final verification evidence.

## Pending tasks

### Stage 1 — Project Foundation and Configuration

- [x] Inspect and preserve the existing foundation behavior before changes.
- [x] Define foundational typed contracts for scope, evidence, scenarios, investigation state, and question/status enums.
- [x] Configure PostgreSQL/pgvector, LLM, embeddings, LangSmith, logging, production-rate, and runtime settings.
- [x] Confirm local startup, application liveness, and clear database health reporting with tracing disabled.
- [x] Add and run focused tests for foundation contracts and health endpoints.
- [x] Run and record available dependency, pytest, Ruff, import, and startup checks.
- [x] Verify PostgreSQL authentication and pgvector availability with valid project database credentials.

### Later stages

- [x] Implement domain models, PostgreSQL schema, migrations, and fixed-seed authored-data generation/loading.
- [x] Verify Stage 3's new simulation-derived dataset and Framing constraint case to close Stage 2 final acceptance.
- [x] Implement the seven-station SimPy simulation, buffers, faults, repairs, calendars, scenarios, and uncertainty.
- [x] Implement deterministic historical analytics and candidate identification.
- [x] Implement evidence ingestion, exact/lexical/vector retrieval, linking, and qualified cause assessment.
- [x] Implement exactly four agents and controlled LangGraph workflows.
- [x] Implement and verify the read-only API and local web interface.
- [ ] Complete validation, documentation, packaging, presentation, and rehearsal.

## Validation commands and actual results

Commands below record the earlier Stage 1 checks. Current Stage 2 checks and
results are recorded in the execution record below.

| Command | Actual result |
| --- | --- |
| `poetry check` | Shell command unavailable (`poetry` is not on PATH); equivalent `\.venv\Scripts\python.exe -m poetry check` passed: `All set!`. |
| `poetry run pytest` | Poetry shell command unavailable; equivalent `\.venv\Scripts\python.exe -m pytest` passed: 8 tests passed. |
| `poetry run ruff check .` | Poetry shell command unavailable; equivalent `\.venv\Scripts\ruff.exe check .` passed: `All checks passed!`. |
| `\.venv\Scripts\python.exe -m pytest tests/unit/test_foundation.py` | Passed: 7 tests passed. |
| `\.venv\Scripts\python.exe -m pytest` | Passed: 8 tests passed, including the live PostgreSQL/pgvector integration test. |
| `\.venv\Scripts\ruff.exe check .` | Passed: no lint errors. |
| `\.venv\Scripts\python.exe -c "... import ..."` | Passed: all required Python imports loaded; application title and contract state were printed. |
| `\.venv\Scripts\python.exe -c "... TestClient(app) ..."` | Passed: `/health` returned HTTP 200 and `/health/database` returned HTTP 200 with `misconfigured` when `DATABASE_URL` was absent. |
| Configured PostgreSQL health check using local `.env` | Passed: `status=healthy`, `database_connected=true`, `pgvector_available=true`, and `vector_operations_available=true`. |
| Live SQLAlchemy pgvector operation | Passed: `SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector` returned distance `1.0`. |
| `poetry run alembic upgrade head` | Not run; the planned business schema is not implemented yet. |

Repository inspection was completed before implementation. Those inspection commands are not implementation validation results.

## Blockers and decisions

### Blockers

- None for Stage 1.
- None remaining for Stage 3 or Stage 2 final acceptance.
- None remaining for Stage 4. Model-exclusive machine states remain an explicit
  schema limitation, not fabricated measurements or a blocker to qualified analytics.
- None for Stage 5. The configured provider, live embeddings and 17 synthetic
  semantic/hybrid acceptance cases are verified; general real-plant relevance
  remains outside the scope of these checks.
- None for Stage 6. Live OpenAI planning, grounded evidence selection, the full
  combined experiment, audit storage and preservation checks passed. Optional
  remote LangSmith delivery was not tested because tracing is disabled.
- Resolved incident: PostgreSQL reported `DiskFull` (53100). The user freed disk space and restarted the stopped service. Database recovery, full dataset load/replay, authored-data preservation and final tests all passed afterward. The agent did not delete data/files to resolve the incident.

### Decisions

- Preserve the four-agent architecture exactly: Orchestrator/Planner, Data and Analytics, Knowledge and Root-Cause, and Simulation.
- Preserve PostgreSQL with pgvector, SQLAlchemy 2.x, Alembic, SimPy, LangGraph, FastAPI, LangSmith, Poetry, pytest, and Ruff.
- Keep the project as a modular monolith with synthetic, read-only source connectors.
- Keep database connectivity lazy: application liveness must work without a database, while database readiness reports missing configuration, connection failure, or missing pgvector explicitly.
- Use the configured local PostgreSQL database and existing pgvector installation; do not recreate the database or reinstall the extension.
- Use this file as the implementation progress record; update task and stage statuses only after the corresponding work has actually been implemented and verified.
- Do not mark a task or stage complete based on planned work, code inspection alone, or an unexecuted validation command.

## Stage 2 execution record — 2026-11-07

**Implementation status: Completed. Final acceptance was initially pending Stage 3
output and is now closed; see the final Stage 3 verification below.**

Read all four project documents and the attached request before changes. The
Stage 1 baseline passed all 8 tests. Existing settings, engine/session creation,
declarative base, logging, health endpoints, and pgvector installation were reused.
No dependencies were added or changed. No Git commit was made.

### Implemented and verified

- [x] Manufacturing enums and validated date/seed/volume/dataset configuration.
- [x] 21 typed SQLAlchemy table mappings with UUIDs, required columns, FKs,
  positive intervals, allowed categories/states, uniqueness, and useful indexes.
- [x] Dated shifts and explicit planned-break exclusions; durations computed
  from timestamps in PostgreSQL.
- [x] Original source IDs/fields/text, file provenance, explicit incident links,
  and separately labeled inferred evidence links.
- [x] SOP metadata/content/sections; generated full-text column and GIN index;
  nullable pgvector/model columns, with no fabricated embeddings.
- [x] Initial business migration generated, manually reviewed, safely applied,
  and tested in isolated schemas.
- [x] Fixed-seed authored event fixtures and source projections for all seven
  source systems, including missing notes, irrelevant notes, delayed/open and
  unlinked maintenance, and invalid/missing sensor values.
- [x] Transactional loading, per-dataset UUID namespace, advisory lock,
  idempotent replay, conflict rejection, counts and stored-value verification.
- [x] CSV/JSONL exports, original SOP text files, manifest, read-only source
  connectors, and explicit generation CLI.
- [x] Initial 30-day fixture generated, validated, loaded and replayed without
  duplicates.
- [x] Framing-focused evidence fixture with checked authored fault durations.
- [x] Unit/integration tests, migration consistency check, imports/compilation,
  Poetry configuration check, and Ruff.
- [x] Final shared history produced by the seven-station SimPy model.
- [x] Confirmed Framing-stronger-constraint expected result using line sensitivity.

### Schema and migration

Migration revision: **0001**, `alembic/versions/0001_initial_business_schema.py`.

Before migration, the existing target `bottleneck_analyzer` had no tables or
migration revisions. The role was confirmed as `bottleneck_app`; vector 0.8.7 was
already enabled. Upgrade created 21 business tables plus `alembic_version`; it
did not drop or overwrite tables, change credentials, recreate the database, or
install/alter the extension. `alembic check` reports no model/schema differences.

Entities and relationships are documented in
[`design/stage-2-data-model.md`](design/stage-2-data-model.md). Future simulation
configuration/run and investigation-audit tables are schema only and contain no
generated results or agent behavior.

### Initial dataset and counts

- Name: `stage2-30day-v1`.
- Generator version/provenance: `authored-fixture-v1` / `authored_fixture`.
- Seed: **42**.
- Period: **2026-09-01 00:00 UTC through 2026-10-01 00:00 UTC**, end exclusive.
- Calendar: 30 days, two eight-hour shifts/day, 30-minute planned break per shift.
- Requested volume: 345 vehicles/shift, alternating SUV/Sedan. This yields the
  illustrative 46 JPH reference by construction; it is not calibrated simulation output.
- Content hash: `cdea3a7b8470b6e0e2779f8bea6e539cdf73789862dd2ee646ca48919c2d41f1`.
- Manifest: `data/raw/stage2-30day-v1/manifest.json`.

| Entity | Persisted records |
| --- | ---: |
| Dataset | 1 |
| Station | 7 |
| Buffer | 6 |
| Vehicle model | 2 |
| Shift | 60 |
| Calendar exclusion | 60 |
| Vehicle | 20,700 |
| Production record | 144,900 |
| Station-state event | 2,520 |
| Fault event | 420 |
| Maintenance work order | 375 |
| Andon event | 280 |
| Shift handover note | 144 |
| Historian observation | 420 |
| SOP document | 7 |
| SOP section | 14 |
| Source record | 149,080 |
| Evidence link | 1,533 |
| Model configuration | 0 |
| Simulation run | 0 |
| Investigation audit | 0 |

Source breakdown: MES 144,900; SCADA 2,940; historian 420; CMMS 375; Andon 280;
shift notes 144; SOP documents/sections 21. Sensor qualities: 140 good, 140 bad,
140 missing. Evidence links: 1,449 direct and 84 inferred.

### Actual Stage 2 validation results

Commands were executed from the project root using the installed `.venv` Python
3.12 environment. The Poetry executable is not on PATH, but its module is available.

| Executed command or check | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m alembic history` before migration | No existing revisions. |
| SQLAlchemy inspection before migration | Correct database/role, no tables, vector 0.8.7 present. |
| `.\.venv\Scripts\python.exe -m alembic upgrade head` | Passed; applied initial revision 0001. |
| `.\.venv\Scripts\python.exe -m alembic current` | `0001 (head)`. |
| `.\.venv\Scripts\python.exe -m bottleneck_analyzer.data.generators.cli` | Passed; first load `created: true`, integrity checks and stored-value comparison succeeded. |
| Same generation command repeated | Passed; `created: false`, identical hash/counts, no duplicates. |
| `$env:STAGE2_TEST_POSTGRES='1'` then `.\.venv\Scripts\python.exe -m pytest -q` | **40 passed**, including all Stage 1 tests, pure generator tests, and opt-in migration/constraint/load tests. |
| `.\.venv\Scripts\python.exe -m alembic check` | Passed; no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m poetry check` | Passed; `All set!`. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic` | Passed; no compilation errors. |
| Mapper/import check with `configure_mappers()` | Passed; 21 mapped tables. |
| `.\.venv\Scripts\ruff.exe check .` | Passed; all checks passed. |
| Read-only database audit after live tests | All seven sources present; expected sensor/link counts; zero `stage2_test_%` schemas remain. |

During development, checks found a break-boundary error in authored booking slots
and an Alembic version-table comparison issue; both were corrected before the
passing run. Replay also tests rejection of changed stored values. The old Stage 1
test assumption that metadata must stay empty was updated to check that engine
creation remains lazy after business models are registered; the original engine,
driver and session assertions remain.

Live write tests require explicit `STAGE2_TEST_POSTGRES=1`. They create uniquely
named schemas inside rollback-only transactions, apply the real migration there,
verify all business tables are in that schema, and verify cleanup. They do not
modify public development data. The role lacks CREATEDB privilege, so no test
database was created and no role/credential changes were attempted.

No separate type checker is configured. Compilation/import checks and executed
tests passed; no unexecuted type-check result is claimed.

### Limitations and next stage

The primary plan requires simulation-derived history. This task excludes Stage 3
simulation implementation, so the initial dataset is explicitly an authored
fixture. It verifies data integrity and ingestion, not finite-buffer propagation,
calibration, line causation, or scenario gains. The Framing fixture verifies higher
authored fault duration only; line-level constraint sensitivity is unverified.

**At the Stage 2 handoff, implementation was complete and final acceptance was
pending Stage 3 output. That acceptance has since been closed.**
The implementation and its 40-test verification record stand as completed work.
The original schedule is unchanged: Stages 2 and 3 share Day 1 hours 1–3.5.

The handoff is sequential:

1. Stage 3 consumes the completed Stage 2 contracts, schema, migration, and
   authored-data/source-loading pipeline. Its entry dependencies are satisfied.
2. Stage 3 builds the SimPy model and generates a new simulation-derived dataset
   under a fresh identity, preserving the authored fixture.
3. Validate/load the new dataset through the Stage 2 pipeline and verify the
   remaining simulation-derived history and Framing constraint acceptance evidence.
4. Record the actual results in this file and close Stage 2 final acceptance once
   those checks pass. Do not repeat or reopen completed implementation solely
   because the acceptance evidence arrived later.

At that earlier tracking correction, Stage 3 remained Not Started. The subsequent
Stage 3 implementation and verification are recorded below.

## Stage 3 execution record — 2026-11-08

**Status: Completed. The storage incident described below was resolved, and all
final acceptance checks passed.**

### Implemented

- [x] Typed synthetic processing/failure/calendar/release/mix/scenario parameters.
- [x] Seven SimPy station workers, six finite buffers and bounded source admission.
- [x] Model-specific positive processing distributions, actual blocking and starvation.
- [x] Operating-time failures, calendar-time serialized repairs, and remaining-work resumption.
- [x] Two-shift calendars, break/overnight pauses, exclusive state accounting and censored WIP.
- [x] Line/station metrics, queue/WIP integrals, model/shift/hour throughput and state conservation.
- [x] Separate indexed random streams, paired experiments, uncertainty and capacity sensitivity.
- [x] Both targeted interventions: repair duration ×0.70 and failure rate ×0.70 (MTBF ÷0.70).
- [x] Transparent calibration grid with independent evaluation seeds.
- [x] Simulation provenance, source projections, actual MES/fault evidence links, configuration/run storage and referenced SOP reuse.
- [x] Explicit CLI commands for baseline, replication, calibration, scenario, sensitivity, assessment, export and persistence.
- [x] Framing stress-case generation and measurement; reference dataset saved before the storage failure.
- [x] Full 30-day result/history validation and reproducible source export.
- [x] Independent unit tests, Ruff, compilation and Poetry configuration checks.
- [x] Commit and replay the 30-day simulation dataset after disk recovery.
- [x] Verify the authored fixture and committed Framing dataset after recovery.
- [x] Complete a clean full-suite run and final Alembic comparison.
- [x] Close Stage 3 and Stage 2 final acceptance after those checks pass.

### Compatibility changes and migration

Revision **0002** extends the equipment-category check constraint for mechanical,
electrical, sensor and other equipment faults. It was reviewed and applied to the
existing database without changing original rows, credentials or extensions.
The user approved updating only the pre-existing migration test's revision
assertion from a hardcoded `0001` to the actual Alembic head. Other existing tests
were retained. Stage 2's loader now takes an explicit validator and history
provenance, defaulting to its original authored behavior; simulation supplies its
own validator for partial WIP, cross-shift operations and physical repair intervals.
No dependencies were added and no Git commit was made.

### Calibration, uncertainty and constraint evidence

Five three-day calibration seeds **11–15** evaluated only the declared Hemming
robot mean-repair grid: 360, 480, 600 and 720 seconds. Mean JPH was respectively
51.284444, 49.244444, 47.160000 and 45.311111. The selected **720 seconds** met the
45–47 JPH calibration tolerance. All other assumptions stayed fixed. Calibration
is against the exercise's illustrative reference, not real plant data.

The independent **20 paired 30-day experiments**, seeds **1001–1020**, produced:

| Metric | Actual result |
| --- | --- |
| Baseline mean JPH | 46.255889 |
| Baseline standard deviation | 0.429603 |
| Baseline minimum–maximum | 45.306667–46.880000 |
| Baseline 95% mean interval | 46.054831–46.456947 |
| Scenario mean JPH | 49.609000 |
| Scenario standard deviation | 0.348899 |
| Scenario minimum–maximum | 48.748889–50.022222 |
| Scenario 95% mean interval | 49.445712–49.772288 |
| Paired mean gain JPH | 3.353111 |
| Paired gain 95% interval | 3.275210–3.431012 |
| Mean throughput improvement | 7.249% |
| Observed scheduled robot-fault loss reduction | 24.714% |

The 0.70 repair multiplier is exact for matching sampled repairs. Realized loss
reduction differs because exposure/event counts and censoring change with flow.
The 95% intervals use Student-t statistics across seeds, not model-error bounds.

Separate five-seed, three-day sensitivity experiments (**2001–2005**) identify
**Hemming before and after intervention; no constraint move was observed**. Its
10% processing speed-up gained 4.826667 JPH before intervention (95% interval
4.689556–4.963777) and 4.973333 afterward (4.616603–5.330064). Other tested stations
had zero gain in these experiments. All 20 long baseline runs also ranked Hemming
first observationally; the ranking alone is not treated as proof.

The separate failure-rate method completed **20 three-day pairs**, seeds
**4001–4020**: baseline 46.454444 JPH, scenario 49.637778, paired gain 3.183333
(95% interval 2.751442–3.615225). This shorter mechanism-validation experiment
does not replace the primary 30-day comparison.

The Framing fixture uses a declared 90-second mean Framing processing assumption.
Five three-day sensitivity seeds **3001–3005** identify Framing even though Hemming
has the largest fault loss. The saved seed-3001 case completed 1,716 vehicles at
38.133333 JPH. An idealized one-day line achieved 59.6 JPH versus the 60 JPH design
reference (startup included). Raising source opportunities from 65 to 90 JPH left
the three-day reference output at 45.8 JPH in both cases; releases do not force 46.

### Dataset generation and persistence

The **validated export** is `sim-30day-baseline-v1`, seed **1001**, simulation
version `simpy-line-v1`, 2026-09-01 through 2026-10-01 UTC, 50/50 stochastic mix,
450 scheduled production hours. The single retained run completed **21,096**
vehicles at **46.88 JPH**, from **21,126** admissions with **30** final WIP. This
single run is distinct from the 20-replication mean above.

| Entity | Generated and persisted records (verified after recovery) |
| --- | ---: |
| Station | 7 |
| Buffer | 6 |
| Vehicle model | 2 |
| Shift / calendar exclusion | 60 / 60 |
| Vehicle | 21,126 |
| Completed station production record | 147,736 |
| Station-state interval | 222,115 |
| Physical fault / historian observation | 1,017 / 1,017 |
| Maintenance work order | 762 |
| Andon event | 678 |
| Handover note | 264 |
| Source record | 373,589 |
| Evidence link | 4,698 |
| Model configuration / simulation run | 1 / 1 |

SOP content is referenced from `stage2-30day-v1`, not copied. The baseline export
hash is `23b496836dcc2d35a7922a5c6d2c75061212447ee7808f1964ba1019ab609394`.
CSV/JSONL exports plus manifest are in `data/raw/sim-30day-baseline-v1/` and total
approximately 188 MB. A second export-only run passed validation and reused that
manifest. The full-history process was observed at approximately 810 MB RAM.

The initial database load failed with SQLSTATE 53100 during station-event
insertion. Post-recovery checks confirmed rollback; the subsequent full load and
replay passed, as detailed in the final recovery evidence below.
The separately committed `sim-framing-validation-v1` case has 1,733 vehicle rows,
12,038 station operations, 20,672 states, 91 faults, 33,045 source records, and 421
links. Its hash was reverified after recovery. The authored fixture's original
hash and every generated stored value were also reverified unchanged.

### Actual checks

| Executed check | Actual result |
| --- | --- |
| Initial focused simulation tests | 17 passed. |
| Isolated integration suite before storage failure | 13 passed. |
| Expanded simulation tests before CLI error handling | 21 passed. |
| Full suite during disk/recovery event | 61 passed; one failure and two errors in database operations. Not a passing full-suite result. |
| Final independent unit suite (`pytest tests/unit -q --tb=short`) | 51 passed, including safe disk-full CLI reporting. |
| Ruff | Passed after final code changes. |
| Compilation (`compileall -q src tests alembic`) | Passed, exit 0. |
| Poetry module check | Passed, `All set!`. |
| Full suite after recovery | 64 passed in 55.98 seconds, exit 0. |
| Final Alembic/database comparison | Passed after recovery: no new upgrade operations, head 0002. |
| Original plan checksum | Matches the unchanged reference copy. |

Detailed commands, assumptions, report filenames and remaining limitations are in
[`design/stage-3-simulation.md`](design/stage-3-simulation.md). Reports and generated
data are ignored by Git. There is no separate type checker configured.

### Acceptance and handoff

Stage 3 and Stage 2 final acceptance are **Completed**. Stage 4 can safely begin
using the verified database and simulation interfaces, and remains **Not Started**.
No simulation results or reduced datasets were substituted for the failed load.

### Final recovery and acceptance evidence

The user freed C: to approximately 10.8 GB and restarted `postgresql-x64-17` after
Windows denied service-control access from the agent session. Read-only checks
then confirmed healthy PostgreSQL/pgvector, no committed partial baseline, no
orphaned test schemas, and unchanged authored/Framing hashes. The failed load had
rolled back. No credentials, extensions, database identities or original records
were replaced.

The full 30-day load was retried and **committed successfully**. An identical
second run returned **`created: false`** after checking counts and every generated
stored value; its fingerprint remained
`23b496836dcc2d35a7922a5c6d2c75061212447ee7808f1964ba1019ab609394`.
The original Stage 2 generator was also replayed: it returned **`created: false`**
after full stored-value verification, retaining original hash
`cdea3a7b8470b6e0e2779f8bea6e539cdf73789862dd2ee646ca48919c2d41f1`.
All CSV/JSONL source exports were parsed successfully (373,589 source records;
SOP content remains referenced).

Final executed checks:

- **Full pytest suite: 64 passed in 55.98 seconds**, exit 0, with
  `STAGE2_TEST_POSTGRES=1` and `--tb=short`. This supersedes the interrupted run.
- **Ruff: passed. Compilation: passed (exit 0). Poetry check: passed.**
- **Alembic check: passed**, no new upgrade operations; **current revision: 0002**.
- **Database audit: passed** for all three dataset hashes and exact baseline
  persisted counts, including 21,126 vehicles, 147,736 operations, 222,115 states,
  1,017 faults and 373,589 source records.
- **Temporary test schemas: zero** after the final suite; original fixture and
  committed Framing dataset remain present with their expected hashes.
- C: retained approximately **10.6 GB free** at the final audit.

`data/processed/stage3/persisted-baseline.json` records the successful load.
The immutable report retains its initial `created: true`; the verified replay
reported `created: false` in the terminal without replacing the report. Technical
assumptions and limitations remain documented; calibration is not plant validation.

## Stage 4 execution record — 2026-11-08

**Status: Completed. Stage 5 is ready to begin and remains Not Started.**

Read the attached Stage 4 request, AGENTS, original plan, roadmap, this status
record, Stage 2/3 technical documents and README. Inspected actual schemas,
configuration/session creation, generator/storage, simulation projection and
source fields, existing tests, indexes, saved reports and all three persisted
datasets before implementation. The analytics package previously contained only
its initializer. No unrelated code was rewritten.

### Implemented and verified

- [x] Dataset-explicit typed scope/result contracts reusing shared scope/evidence types.
- [x] Repeatable-read, PostgreSQL-enforced read-only public analysis interface.
- [x] Bound, explicitly dataset-filtered aggregate queries; no raw-export loading or N+1 loop.
- [x] Unioned shift calendars, explicit break subtraction, aware periods and UTC-hour handling.
- [x] Admissions/completions, initial/final and average/max WIP, flow time, JPH and design gap.
- [x] Station operations, active service, elapsed duration, exclusive states, coverage and queue metrics.
- [x] Dated shifts, model JPH contributions, UTC-hour groups, partial/closed-period behavior.
- [x] Transparent candidate scoring, individual indicators, support/conflicts and evidence strength.
- [x] Sample/coverage thresholds, abstention, segment changes and dated-shift persistence counts.
- [x] Aggregate references and bounded real source UUID/system/source-ID samples.
- [x] Separately labeled persisted simulation reference and configuration-checked optional assessment.
- [x] CLI, opt-in PostgreSQL tests, baseline/Framing comparison and documentation.

### Actual results

`sim-30day-baseline-v1` remains simulation-derived with its original UUID/hash:
21,126 admissions, 21,096 completions, 30 final WIP and 450 scheduled hours give
**46.88 JPH**, **13.12 JPH design gap**, and **5,904 design-gap bodies**. This gap
is not station-specific recoverable output. SUV/Sedan completions are
10,461/10,635, contributing 23.246667/23.633333 JPH. Mean flow time is
3,771.414151 seconds and average WIP is 30.922847.

**Hemming** is the overall historical leader and leads all 60 dated shifts.
The two model proxy rankings lead with **Framing**, explicitly qualified because
the schema cannot assign shared machine states exclusively to SUV/Sedan. They
are not proof of model-specific line constraints. There are 24 pooled UTC-hour
groups, with null JPH and no asserted leader in closed hours.

Counts, scheduled hours, flow/WIP, station operations/state durations/queue
integrals, individual dated shifts and UTC-hour buckets match the independently
stored Stage 3 simulation metrics. The 46.88 retained single-run JPH is correctly
distinct from the 46.255889 mean of 20 independent replications. Matching saved
sensitivity evidence remains separate from observational scores.

The existing `sim-framing-validation-v1` gives **1,716 completions**, **38.133333 JPH**
and **Framing** first, although Hemming has the greatest faulted time. No simulation
assumptions were changed and no long simulation experiment was rerun.

### Validation commands and actual results

Commands used the existing Python 3.12 `.venv` from the project root.

| Executed command/check | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_analytics.py -q --tb=short` | **18 passed in 0.78 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest tests/integration/test_analytics.py -q --tb=short -x` | **7 passed in 85.11 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest -q --tb=short` | First full run **89 passed in 122.52 seconds**. |
| Same full suite after final numeric/order and per-shift/hour assertions | **89 passed in 121.90 seconds**, exit 0. |
| `.\.venv\Scripts\ruff.exe check .` | **Passed**, all checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic` | **Passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m poetry check` | **Passed**, `All set!`. |
| `.\.venv\Scripts\python.exe -m alembic check` | **Passed**, no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m alembic current` | **0002 (head)**, unchanged. |
| Full baseline CLI with matching comparison/assessment artifacts | Passed; 21,096 completions, 450 hours, 46.88 JPH, Hemming, 86 segments. |
| Query audit / measured full analysis | **15 statements**, SELECT/WITH/SET only; **33.326 seconds** while another test run was active. |
| Post-suite read-only dataset audit | All three provenance labels/hashes unchanged; baseline counts 21,126 vehicles, 147,736 operations, 222,115 states, 373,589 sources. |
| Post-suite temporary-schema audit | **Zero** `stage2_test_%` schemas remain. |
| Original implementation-plan checksum | Still `AA250999107FDBFDC56F88DD6E91AC3DBCAAD41E01B46BB634EF71A9B7A6AD1D`. |

The full-suite PowerShell sequence is:

```powershell
$env:STAGE2_TEST_POSTGRES = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Early development checks exposed a slow interval nested loop, session-timezone
dependence, and one-microsecond queue-max artifacts. These were corrected with
materialized UTC-hour slices, transaction-local UTC, and a declared two-microsecond
maximum-resolution threshold. Final passing results above supersede failed or
cancelled exploratory checks. No separate type checker or peak-memory benchmark
is claimed. The measured structured report was approximately 3.3 MiB; raw histories
remain in PostgreSQL.

### Files and decisions

Created six analytics modules: `contracts.py`, `calendar.py`, `repository.py`,
`candidates.py`, `service.py`, `cli.py`; two analytics test modules; and
`docs/design/stage-4-analytics.md`. Updated README, roadmap and this status file.
Local JSON reports under `data/processed/stage4/` are ignored by Git.

No dependencies, migration, existing tests, shared domain contracts, simulation
code, generators, database credentials, extension, or persisted datasets were
changed. Temporary test fixtures exist only in rollback-only isolated schemas.
No Git commit was created. No Stage 5–8 behavior was implemented.

### Limits and handoff

No blockers remain for Stage 4 acceptance. Scores are documented heuristics, not
probabilities or proof of real-plant constraints. Model-exclusive state attribution
is unsupported and null; model evidence is capped at moderate. Closed periods
have no JPH, missing/overlapping states are explicit, and completed-visit means can
have censoring/boundary bias. The design gap remains separate from simulated
recoverable gain. Stage 5 may use the structured candidate scopes and source IDs
for evidence retrieval; it has not been started.

## Stage 5 execution record — 2026-11-08

This initial implementation record preceded live semantic acceptance. The latter
was pending at this point and is closed in the follow-up record below.

**Status: Completed for implementation and local acceptance. Stage 6 remains
Not Started and is ready to begin.**

Inspected the attached request, AGENTS, original plan/roadmap/status, Stage 2–4
technical documents, actual mappings/indexes/source projections/links, typed
analytics contracts, settings, test fixtures and the three existing datasets.
The retrieval package previously had only an initializer. Official OpenAI
documentation was checked for the optional real embedding adapter.

### Implemented and verified

- [x] Explicit dataset/station/aware-period request, bounded results and validated exact UUIDs.
- [x] Read-only snapshot interface, fixed bound SQL, dataset/station/time/system/shift/hour filters.
- [x] Exact incident/work-order/source resolution before FTS/vector searches; FKs work without graph rows.
- [x] PostgreSQL English full-text search through the existing generated vector and GIN index.
- [x] Actual pgvector cosine search with model identity and dimension guards, verified with isolated numeric fixtures.
- [x] Missing vectors/configuration/provider failures preserve exact/lexical results and disclose unavailable semantics.
- [x] Exact-priority rank fusion and identity-based deduplication preserving every matching method and original link type.
- [x] Original source text/JSON/IDs/path/timestamp/station/incident/version metadata and explicit rendering basis.
- [x] Whole short records, existing SOP sections and stable virtual fallback chunks; no duplicated source rows.
- [x] Explicit null-only vector enrichment with validated metadata, replay skipping and atomic failure behavior.
- [x] One-way Stage 4 adapter, candidate indicator/source references and scope validation; no recalculation.
- [x] Four qualified assessment labels, abstention, visible contradictions, bad-sensor exclusions and untrusted-text handling.
- [x] CLI, unit/integration tests, full regression, technical documentation and preservation audits.

### Actual baseline verification

The live Stage 4-to-Stage 5 check selected `sim-30day-baseline-v1` and Hemming.
Analytics remained **46.88 JPH**, **Hemming** leading. Retrieval fetched **6 exact**
and **60 bounded lexical** matches, returned **20** records and disclosed truncation.
Source systems included Andon, CMMS, SCADA and historian. With the copied candidate
fault-occupancy indicator and linked incident records, the assessment was a
qualified **supported_hypothesis** about equipment interruptions. It did not claim
a recorded component cause, line-level causal loss or recoverable throughput gain.

Measured retrieval (excluding analytics) took **1.936 seconds**, with **16 SQL
statements including savepoint control** during another test run. Statements were
SELECT/WITH/SET/SAVEPOINT/RELEASE only. The initial linked report was 43,680 bytes
before the final original-text provenance fields were added. These are measured
observations, not guarantees. Local reports/audits are under `data/processed/stage5/`.

Actual development embedding provider/model/key remain unconfigured and all
stored embedding/model pairs remain null. Semantic retrieval correctly reports
unavailability. The OpenAI HTTP contract was tested offline and real pgvector
storage/search in rollback-only schemas used explicitly synthetic numeric geometry
fixtures; no live external API call or semantic-quality evaluation is claimed.
The documented configurable setup is OpenAI `text-embedding-3-small`, 1,536 dimensions.

### Validation commands and actual results

| Executed command/check using existing `.venv` | Actual result |
| --- | --- |
| `python -m pytest tests/unit/test_retrieval.py -q --tb=short` | **24 passed in 0.13 seconds**. |
| `STAGE2_TEST_POSTGRES=1`, then `python -m pytest tests/integration/test_retrieval.py -q --tb=short -x` | **10 passed in 13.45 seconds**. |
| Final focused retrieval unit + integration suite | **34 passed in 13.67 seconds**. |
| Final complete suite, `STAGE2_TEST_POSTGRES=1`, `python -m pytest -q --tb=short` | **123 passed in 103.47 seconds**, exit 0. |
| `ruff check .` | **Passed**, all checks passed. |
| `python -m compileall -q src tests alembic` | **Passed**, exit 0. |
| `python -m poetry check` | **Passed**, `All set!`. |
| `python -m alembic check` | **Passed**, no new upgrade operations detected. |
| `python -m alembic current` | **0002 (head)**, unchanged; no migration created. |
| Live read-only analytics-to-retrieval check | **Passed**, baseline metrics unchanged and qualified linked evidence returned. |
| Public-table preservation audit | All **21 tables** matched row counts/content digests; source-record count **555,714** unchanged. |
| Saved Stage 3 reports audit | Every saved JSON report SHA-256 matched before/after verification. |
| Post-suite embedding/schema audit | **0** populated embedding/model pairs; **0** leftover `stage2_test_%` schemas. |
| Original plan checksum and protected-code diff | Plan checksum unchanged (`AA250999107FDBFDC56F88DD6E91AC3DBCAAD41E01B46BB634EF71A9B7A6AD1D`); analytics, simulation, data, DB/domain, migrations and dependency files unchanged. |

The PowerShell full-suite sequence was:

```powershell
$env:STAGE2_TEST_POSTGRES = '1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Early checks found an untyped nullable SQL parameter and a blank-section fallback
edge case; both were fixed before final verification. Failed exploratory outputs
are superseded by the passing results above. No type checker is configured.

### Files, configuration and safety

Created eight modules under `retrieval/`: `contracts.py`, `repository.py`,
`chunking.py`, `embeddings.py`, `indexing.py`, `evidence.py`, `service.py`, `cli.py`;
`tests/unit/test_retrieval.py`, `tests/integration/test_retrieval.py`; and
`docs/design/stage-5-retrieval.md`. Modified only typed embedding settings in
`core/config.py`, `.env.example`, README, roadmap and this status record.

No files were deleted. No dependencies or migrations were added. The actual `.env`,
credentials, database/extension, existing datasets, source fields, simulation
assumptions, Stage 4 contracts/calculations and prior tests were preserved.
Embedding enrichment ran only in isolated rollback-only schemas. No Git commit
was created and no Stage 6 agent, workflow, business API or UI was implemented.

### Limits and handoff

No Stage 5 implementation/local-acceptance blocker remains. Live embedding API
behavior and retrieval quality remain unverified without external configuration;
current development semantic retrieval is unavailable rather than simulated.
SOPs owned by the authored dataset need an explicit request for that dataset;
baseline retrieval does not silently cross that boundary. Graph expansion is
bounded/one-hop, fallback scores are source-level, and shared evidence has no
model-exclusive attribution. Evidence labels are conservative deterministic
assessments; text is never causal proof or an instruction to act.

Stage 6 can consume validated analytics, simulation and retrieval interfaces.
Its exactly-four-agent orchestration remains **Not Started**.

## Stage 5 live semantic acceptance follow-up — 2026-11-08

**Status: Completed, including live provider/indexing/relevance acceptance.**

The user configured `.env`, successfully tested `text-embedding-3-small` at 1,536
dimensions, and indexed 20 Hemming records. They then explicitly authorized
completion of the remaining indexing, quality tests, regression checks and tracking.
This authorization permits derived embedding enrichment while preserving source
facts; it does not permit changing production history or starting Stage 6.

### Live indexing and preservation

| Dataset | Eligible/populated text records | Existing / newly indexed |
| --- | ---: | ---: |
| `sim-30day-baseline-v1` | 1,644 | 20 / 1,624 |
| `sim-framing-validation-v1` | 147 | 0 / 147 |
| `stage2-30day-v1` | 753, including 14 SOP sections | 0 / 753 |
| Total | **2,544** | **20 / 2,524** |

All three datasets have embeddings for relevant text across all seven stations.
The identity is `openai:text-embedding-3-small:1536:source-v1`; every populated vector
has dimension 1,536. Empty/structured source rows, stationless irrelevant notes and
sectioned SOP parents were not embedded. This avoids vectorizing hundreds of
thousands of numerical production/state rows that have no searchable prose.

Batching/caching reused genuine embeddings of identical text under the same model.
Only **22 new texts in 7 provider requests** were needed to enrich the 2,524 rows.
Compatible existing vectors were preserved. Indexing uses batches of at most 50
rows, with no dataset recreation, source duplication or automatic startup work.
A live replay skipped 50/50 indexed sources, generated 0 vectors and made **0 API requests**.

The index runner's before/after audit matched row counts and source-fact content
digests for all 21 business tables, excluding only the two explicitly authorized
derived fields. Original source IDs/text/JSON, paths, timestamps, relationships,
production records, simulation runs/configuration and all dataset hashes remain
unchanged. Saved Stage 3 JSON report SHA-256 values also match.

The first sandboxed request failed before its first batch committed. Retrying with
network access succeeded. The completed run is `live-index-v2.json`; its elapsed
time was **86.60 seconds**, including the two full source-fact audits. The failed
attempt is not counted as successful indexing evidence. No credential was printed
or placed in documentation.

### Relevance measurement and cutoff

The original 0.4 maximum cosine distance required similarity ≥0.6. Eight labeled
calibration probes found legitimate broad repair at **0.5363**, electrical repair
at **0.5889**, and SOP approval at **0.5982**; those were being excluded. Unrelated
food/travel probes scored only **0.0473/0.0060**. Based on that separation, the
default maximum distance is now **0.5** (minimum similarity 0.5).

A separate held-out fixture and boundary/hybrid checks passed **17/17** live cases:

- Robot repair paraphrase **0.6428** and electrical paraphrase **0.5399** return
  records with the expected fault categories.
- Framing-dataset retrieval returns the correct independent dataset/station.
- SOP reporting **0.7307** and approval **0.5804** return the expected section
  numbers with document IDs/versions.
- Two held-out unrelated recipe/currency questions return zero records.
- Every baseline station is explicitly tested and returns only its own records.
- The user's original broad repair question now returns relevant records (**0.5363**).
- Hybrid lookup preserves direct exact priority and deduplicates the same source
  across exact/lexical/semantic methods while retaining all methods.
- End-exclusive source-time filtering and foreign-dataset identifier rejection pass.

The 17 cases used **2 provider requests** through the operation-local cache and
took **21.19 seconds**. These are bounded synthetic acceptance examples, not proof
of general retrieval accuracy or plant causation. Query/source text remains
untrusted, and the existing conservative evidence assessments remain in force.

### Compatibility fixes and tests

The source replay verifier previously compared nullable embedding fields as if
they were original source facts. Real enrichment would therefore break normal
dataset replay. It now excludes only `embedding`/`embedding_model` from source-fact
comparison, retaining strict comparison of every other generated field. A new
integration test proves that enriched replay succeeds and changed original text
still fails. No prior tests were weakened or removed.

Indexing now batches unique texts before updates; `CachedEmbedder` provides bounded
operation-local reuse of real vectors for one identity. All generation/validation,
including fallback pooling, completes before the atomic update savepoint.

| Executed validation | Actual result |
| --- | --- |
| Focused retrieval unit/integration tests, opt-in PostgreSQL | **36 passed in 17.55 seconds** (25 unit, 11 integration). |
| Live `stage5_acceptance.py index` | **Passed**, 2,524 new / 2,544 total vectors; preservation audit passed. |
| Live `stage5_acceptance.py probe --cutoff 2` | **Passed**, eight labeled distance probes recorded; cutoff 2 used only for measurement. |
| Live `stage5_acceptance.py validate` | **17/17 passed**, exit 0. |
| Live 50-source indexing replay | **0 indexed, 50 skipped, 0 provider requests**. |
| Full pytest suite with `STAGE2_TEST_POSTGRES=1` | **125 passed in 140.14 seconds**, exit 0. |
| Ruff | **Passed**, all checks passed. |
| Compilation, `compileall -q src tests alembic scripts` | **Passed**, exit 0. |
| Poetry module check | **Passed**, `All set!`. |
| Alembic consistency/current | **Passed**, no new upgrade operations; **0002 (head)**. |
| Post-enrichment Stage 4 baseline analysis | **46.88 JPH**, 21,096 completions, 450 scheduled hours, Hemming leading, unchanged. |
| Final database audit | All three dataset hashes unchanged; **0** leftover test schemas. |

### Files and artifacts

Created `scripts/stage5_acceptance.py` for explicit resumable enrichment,
calibration and acceptance; `tests/fixtures/live-retrieval-quality.json` for
held-out examples. Updated retrieval batching/cache/default cutoff and tests,
`data/storage.py` replay compatibility, README, Stage 2/5 technical documents,
roadmap and this status record. No migration, dependency, simulation, analytics,
domain contract, agent, API or UI change was made.

Ignored artifacts under `data/processed/stage5/` include `live-index-v2.json` and
its before audit, `live-calibration-v1.json`, `live-validation-v1.json`, and
`live-post-index-analytics.json`. Reports require fresh paths. Original plan,
four-agent architecture and two-day schedule remain unchanged. No Git commit
was created. Stage 5 live acceptance is now closed; **Stage 6 remains Not Started**.

## Stage 6 execution record — 2026-11-08

**Status: Completed. Stage 7 is ready and remains Not Started.**

Read the attached task and all nine required project documents. Inspected actual
contracts, source interfaces, PostgreSQL mappings, tests, settings and installed
APIs before implementation. Shared contracts are in `domain/models.py`, not the
request's nonexistent `core/contracts.py`. Reused those actual contracts.
Installed versions include LangGraph 1.2.20, LangSmith 0.14.17 and Pydantic 2.14.3.
No dependency, lock-file, migration, original implementation plan or Stage 1–5
service behavior was changed. Alembic remains at `0002`.

### Implemented and verified

- [x] Exactly four agents: planner/composer, analytics, knowledge and simulation.
- [x] Typed requests, plans, specialist boundaries, refined shared state, results,
  execution events/errors and final response contracts.
- [x] Five Python-registered routes: historical constraint/output, segmentation,
  causes, what-if and combined. LangGraph uses explicit conditional edges and
  bounded steps; it cannot dispatch arbitrary model-generated functions or SQL.
- [x] Existing `analyze()`, `request_from_analytics()`, `retrieve()`, `compare()`
  and `assess_comparison()` interfaces reused without duplicate business engines.
- [x] Scope/UUID/period validation, ambiguity clarification, unsupported-action
  refusal, empty/partial evidence and specialist/provider failure handling.
- [x] OpenAI Responses structured planning, schema-enumerated evidence-ID
  selection and grounded introduction/citation selection. Python preserves
  assessment labels, explanations, contradictions and verbatim excerpts and
  supplies unresolved questions from known evidence limitations.
- [x] Both robot-fault intervention methods, immutable configuration validation,
  paired uncertainty and independent before/after constraint sensitivity.
- [x] Killable simulation worker with configurable scope/replication/runtime
  bounds; final default runtime limit 600 seconds; zero automatic LLM retries.
- [x] Historical/model-contribution/closed-period semantics preserved. The
  validator accepts legitimate shift narrowing and model design-gap nulls.
- [x] Existing PostgreSQL investigation-audit table used for initial, per-node
  and final durable state. Audit failures prevent confirmed completion.
- [x] Data hashes, requested provider/model identifiers, adapter identity,
  simulation version, execution limits, source IDs, seed lists, tool results,
  validation, timings and response are retained. Model aliases are recorded as
  requested aliases, without claiming an exact provider snapshot.
- [x] Optional metadata-only LangSmith client and structured local events;
  automatic full-state cloud tracing disabled; local audit works without tracing.
- [x] Terminal entry point, report output, safe configuration-error reporting,
  example request, explicit live acceptance runner and technical documentation.
- [x] Full regression, final focused output checks and preservation audit passed.

### Live provider and full workflow

Initially the LLM settings were empty. The user configured local OpenAI
`gpt-4o-mini` access while independent implementation/tests continued. The agent
did not print, copy into documentation, or modify the actual API key.

Eight live planning/guard cases passed in **14.44 seconds**, covering historical,
causes, segmentation, repair-duration, failure-rate, combined, ambiguous downtime
and production-write refusal. Live knowledge selection passed with **three**
allowed supporting source IDs. Exact, lexical and semantic retrieval ran with no
unavailable methods. Matching counts remain available in the reports; running
semantic search does not imply every query returned semantic matches.

The complete natural-language question ran through all four agents, shared
validation and composition. Successful audit:
**`b8291895-7348-429e-b84c-fb33992dea4e`**.

| Actual result | Value |
| --- | --- |
| Historical JPH / leading candidate | 46.88 / Hemming |
| Historical design gap | 13.12 JPH; not station-specific recoverable output |
| Retrieved evidence / qualified label | 6 records / `supported_hypothesis` |
| Simulation horizon / replications | 30 days each / 20 paired replications |
| Evaluation seeds | 1001–1020 |
| Simulated baseline mean | 46.255889 JPH |
| Simulated repair-duration scenario mean | 49.609000 JPH |
| Mean paired gain / 95% interval | 3.353111 JPH / 3.275210–3.431012 |
| Separate sensitivity | Five three-day seeds 2001–2005, baseline and scenario |
| Modeled constraint movement | Hemming before and after; no movement |
| Full workflow / simulation duration | 355.09 / 304.34 seconds |

The comparison was actually recomputed using Stage 3. No saved answer, hardcoded
gain, changed historical dataset or shortened replacement experiment was used.
The retained single-run historical JPH remains distinct from the replication mean.

Earlier live attempts safely rejected invalid model output. The final contract
limits the model to selecting source IDs from an enum; Python copies factual
assessment fields and excerpts. The initial 300-second simulation limit also
stopped a run correctly. Raising the configured bound to 600 seconds retained all
20 pairs and sensitivity checks; the successful measured runtime was 304.34 seconds.
Failed attempts remain in audit/report history and are not counted as acceptance.

### Commands and actual results

All commands used the existing Windows `.venv` from the project root. Ordinary
tests use language-model fixtures; paid calls occur only in the explicit live
acceptance commands.

| Executed command/check | Actual result |
| --- | --- |
| `STAGE2_TEST_POSTGRES=1`, `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | **192 passed in 227.36 seconds**, exit 0. Includes the existing 125-test suite and 67 Stage 6 tests. |
| Final focused unit knowledge + PostgreSQL graph checks | **20 passed in 83.94 seconds**, exit 0, after final unresolved-question/citation changes. |
| `.\.venv\Scripts\ruff.exe check . --output-format concise` | **Passed**, all checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic scripts` | **Passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m poetry check` | **Passed**, `All set!`. |
| `.\.venv\Scripts\python.exe -m alembic check` | **Passed**, no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m alembic current` | **0002 (head)**, unchanged. |
| Stage 6 imports and existing FastAPI TestClient startup | **Passed**; `/health` HTTP 200, tracing disabled. |
| `python -m bottleneck_analyzer.workflows.cli --help` | **Passed**. |
| CLI with deliberately invalid PostgreSQL configuration | **Passed**; expected exit 1, safe error, sentinel configuration value not exposed. |
| Live `stage6_acceptance.py planning` | **8/8 passed**, `live-planning-v3.json`. |
| Live isolated `stage6_acceptance.py knowledge --audit ...` | **Passed**, final ID-selection contract in `live-knowledge-v3.json`. |
| Live `stage6_acceptance.py combined` | **Passed**, all required nodes completed; `live-combined-v4.json`. |
| Original-table/report/vector/protected-file preservation | **Passed**, all recorded checks true. |
| Post-test temporary-schema query | **0** `stage2_test_%` schemas remain. |

Full-suite command:

```powershell
$env:STAGE2_TEST_POSTGRES='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Final affected-output checks:

```powershell
$env:STAGE2_TEST_POSTGRES='1'
.\.venv\Scripts\python.exe -m pytest tests/unit/test_knowledge_agent.py tests/integration/test_orchestration.py -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
```

Development checks also caught a test-helper argument conflict and integration
assumptions about shift bounds/model design gaps. Those were fixed in the new
Stage 6 layer, preserving Stage 4 behavior and all prior tests. No unresolved test
failure remains. No separate static type checker is configured or claimed.

### Preservation and files

The before/after snapshot compared all original source facts and counts in the
**20 business tables other than `investigation_audit`**, including model
configurations and simulation runs. Every comparison matched. The three original
dataset hashes/provenance labels remain unchanged. The source-record count stays
**555,714** and all **2,544** embeddings/model identities match the original vector
digest. Saved Stage 3 reports and protected analytics/retrieval/simulation,
migration, dependency, AGENTS and original-plan files match their pre-stage hashes.

The only database additions are **four new investigation audits**: three failed
attempts and the successful combined run. No pre-existing audit rows existed or
were replaced. The successful audit includes model identifiers, limits, full
results/seeds, validation, final response and matching audit ID. Tests created only
rollback-only isolated fixtures, and no temporary schemas remain.

Created:

- `agents/contracts.py`, `planner.py`, `analytics.py`, `knowledge.py`, `simulation.py`.
- `core/llm.py`, `core/observability.py`.
- `workflows/graph.py`, `validation.py`, `audit.py`, `cli.py`.
- `tests/unit/test_orchestration.py`, `tests/unit/test_knowledge_agent.py`,
  `tests/integration/test_orchestration.py`, `tests/fixtures/stage6-combined-request.json`.
- `scripts/stage6_acceptance.py`, `docs/design/stage-6-orchestration.md`.

Package paths above are under `src/bottleneck_analyzer/`. Modified only
`core/config.py`, `.env.example`, README, roadmap and this status document among
pre-existing files. No original service/test, dependency or migration was changed.
No Git commit was created.

Ignored artifacts under `data/processed/stage6/` include preservation snapshots,
live planning/knowledge/combined reports and retained failed attempts. Real local
`.env` and generated reports remain ignored by Git.

### Limits and handoff

No Stage 6 acceptance blocker remains. All data/models remain synthetic;
correlation and model sensitivity are not real-plant causal proof. Evidence
interpretation is deliberately extractive. Model-specific shared machine states
remain unavailable, and filtered simulation baselines require clarification
rather than silently changing the scenario population/calendar. Cloud-dependent
language features fail clearly rather than fabricate a successful answer.

The full local experiment took about six minutes; the configurable runtime bound
does not imply a latency guarantee. Requested model aliases are not pinned
provider snapshots. LangSmith is disabled locally: no remote delivery claim is
made, while optional client/failure paths and live local logs/audit are verified.
Human review remains required and no operational approval was fabricated.

Stage 6 is **Completed**. Stage 7 can safely begin using the validated public
workflow and response contracts. Stage 7 and Stage 8 were not implemented.

## Stage 7 execution record — 2026-11-08

**Status: Completed. Stage 8 remains Not Started.**

Implemented only the approved Stage 7 plan and its admission/security revisions.
Re-read the project instructions, plan, roadmap, status, Stage 2–6 design material,
source contracts, audit lifecycle, tests and dependency configuration. The working
tree was clean at entry; the existing Stage 6 implementation was preserved.
No reset, discard, database recreation, migration, indexing, reseeding or Git commit
was performed. No dependency or lock-file change was necessary.

### Implemented and verified

- [x] Thin FastAPI endpoints around the unchanged `InvestigationWorkflow.run()`.
- [x] Actual dataset/options reads, bounded saved history, investigation submission,
  saved progress, confirmed results and process-local submission reconciliation.
- [x] One bounded executor/slot, fresh workflow per investigation, occupied-slot
  rejection and no second durable queue or audit store.
- [x] Delegate initial audit creation returns after transaction exit; admission
  waits outside the transaction. Graph execution requires accepted admission.
- [x] Deterministic commitment, late commitment, timeout/disconnect, commit-uncertainty,
  duplicate-key, slot retention, final-save failure and shutdown-draining tests.
- [x] Persisted post-node events only, without invented percentages, active-agent
  claims, node-start times or updated-at fields.
- [x] Matching persisted investigation/response/audit IDs required before publishing
  final results; compose checkpoints alone are insufficient.
- [x] All five workflow outcomes preserved independently from HTTP status.
- [x] Loopback-only supported launcher, one worker, no reload or proxy trust;
  Host/Origin checks, restrictive same-origin policy, JSON/body limits and safe errors.
- [x] Lightweight native HTML/CSS/JavaScript interface, question examples, actual
  metadata/scope, explicit scenarios, reconnect, saved history and expandable evidence.
- [x] Historical metrics, retrieved evidence/qualified interpretations, simulation
  uncertainty and final interpretation shown separately with human review.
- [x] Source text rendered with text nodes; protected CSP and asset boundaries;
  raw metadata/file paths, vectors and internal state excluded from public results.
- [x] Existing audit opened through the API and actual UI without rerunning work.
- [x] Complete regression suite, Node tests, startup, lint, compilation, Poetry,
  Alembic and exact original-data/protected-file preservation checks passed.

### Commands and actual results

All Python commands used the existing Windows `.venv`. Full-suite execution used
elevated tool access because Edge GPU subprocesses could not run inside the tool
sandbox. No browser framework or driver was installed.

| Executed command/check | Actual result |
| --- | --- |
| `STAGE2_TEST_POSTGRES=1`, `STAGE7_TEST_SAVED_BROWSER=1`, `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | **229 passed in 386.07 seconds**, exit 0; no skips. Includes all 192 pre-existing tests and 37 Stage 7 tests. |
| Focused Stage 7 unit + PostgreSQL tests | **35 passed in 57.99 seconds**, exit 0. |
| `.\.venv\Scripts\python.exe -m pytest tests/ui/test_browser.py -q --tb=short` during fixture-browser development | **1 passed in 4.35 seconds**, exit 0. Both browser tests subsequently passed in the complete suite with saved-browser opt-in enabled. |
| `node --test tests/ui/client.test.mjs` | **4 passed**, 0 failed/skipped. Tests request construction, GET-only polling/reconnect, all outcomes/metric separation and errors/backoff. |
| `.\.venv\Scripts\ruff.exe check . --output-format concise` | **Passed**, all checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic scripts` | **Passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m poetry check` | **Passed**, `All set!`. |
| `.\.venv\Scripts\python.exe -m alembic check` | **Passed**, no new upgrade operations detected. |
| `.\.venv\Scripts\python.exe -m alembic current` | **0002 (head)**, unchanged. |
| API/runtime/result-schema/application imports | **Passed**. |
| Existing `python -m bottleneck_analyzer.workflows.cli --help` | **Passed**, existing CLI preserved. |
| Supported `python -m bottleneck_analyzer.api.cli`, subprocess with temporary loopback port | **Passed** over actual HTTP: `/health`, `/`, `/static/app.mjs`, `/api/datasets`, `/health/database` all HTTP 200. Child had no accepted work and was terminated after the smoke check; accepted-work draining is verified separately by the runtime test. |
| `python scripts/stage7_acceptance.py --before <initial-snapshot> --saved-audit b8291895-7348-429e-b84c-fb33992dea4e --report data/processed/stage7/acceptance-v1.json` | **Passed**, every preservation check true; saved status/result HTTP 200 and database/vector health healthy. |

Full-suite command:

```powershell
$env:STAGE2_TEST_POSTGRES='1'
$env:STAGE7_TEST_SAVED_BROWSER='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:STAGE2_TEST_POSTGRES
Remove-Item Env:STAGE7_TEST_SAVED_BROWSER
node --test tests/ui/client.test.mjs
```

Early checks found a test-fixture optional-category mismatch, JSONB path operand
typing/null-response handling, and a Windows UTF-8 browser fixture read issue.
These were corrected before the full passing suite. The initial sandboxed Edge
attempt failed on GPU subprocess access; execution outside the sandbox succeeded.
These failures are not counted as passing acceptance. No separate type checker or
unperformed manual browser check is claimed.

### Acceptance scope and preservation

Browser fixtures exercised four question groups plus combined, all five outcomes,
source HTML safety, evidence expansion, saved-result opening and refresh without
another POST. PostgreSQL HTTP integration used the actual Stage 6 graph with
fixture LLMs for historical, segmentation and causes. Existing regression tests
continue to exercise simulation/combined routing and both intervention mechanisms.
All new database writes were in rollback-only isolated schemas.

The PostgreSQL admission fixture uses a real SAVEPOINT release under the outer
rollback; it proves transaction-context exit before the admission gate, not an
independent durable commit. The production adapter delegates unchanged
`PostgresAudit.create()` and waits only after its transaction context returns.
The real existing committed audit was independently read through API/browser.

The saved live combined audit remains
`b8291895-7348-429e-b84c-fb33992dea4e`. Actual API/browser rendering preserves
**46.88 historical JPH**, **46.25588888888889 simulated baseline mean**, six source
records, uncertainty and the six saved component events. The final public result
is **45,150 bytes**, with raw per-run simulation arrays/configuration copies
excluded and the complete original audit unchanged.

Per the user's explicit restriction, Stage 7 made **no paid provider calls and no
new production simulation run**. Saved-result acceptance is labeled as such; no
fresh live combined investigation is claimed.

Preservation compared exact row counts and order-independent full-row digests for
all **22 public tables**, including Alembic and all **four original audits**.
Every comparison matched. Thus all 21 business tables, three datasets, 555,714
source records, 2,544 embeddings/model identities, source links, simulation runs,
model configurations and audit records remain unchanged. No new public audit was
created during acceptance. Temporary test-schema count is **zero**.

Every original protected source file under Stage 1–6, migration/dependency/lock
file, local `.env` digest and saved Stage 3 report SHA-256 matched the entry
snapshot, except the explicitly approved `main.py` API wiring/error sanitization.
The original plan checksum remains
`AA250999107FDBFDC56F88DD6E91AC3DBCAAD41E01B46BB634EF71A9B7A6AD1D`.
No production data was regenerated or embedding field changed. Prior Stage 4/5/6
behavior is also covered by the complete passing regression suite.

### Files and decisions

Created under `src/bottleneck_analyzer/api/`:
`cli.py`, `settings.py`, `runtime.py`, `repository.py`, `schemas.py`, `routes.py`,
`security.py`, and `static/{index.html,styles.css,app.mjs,client.mjs,render.mjs}`.
The existing initializer was preserved.

Created `tests/unit/test_api.py`, `tests/unit/test_api_runtime.py`,
`tests/integration/test_api.py`, `tests/ui/{test_browser.py,client.test.mjs,browser-driver.mjs}`,
`scripts/stage7_acceptance.py`, and `docs/design/stage-7-api-ui.md`.

Modified only `src/bottleneck_analyzer/main.py`, `.env.example`, README, roadmap
and this status document among existing files. No Stage 6 business logic, existing
test, dependency, migration or actual secret configuration was modified.
Ignored reports live under `data/processed/stage7/`. No Git commit was made.

### Limits and handoff

No Stage 7 acceptance blocker remains. Execution and submission reconciliation
are process-local, bounded and not resumable across restart. A lost response does
not prove cancellation; admission may need reconciliation or saved-history review.
Normal shutdown can wait several minutes for accepted work. Public result/text
projections are bounded and disclose truncation; original audits remain authoritative.

The original health probes retain Host compatibility while UI/business/docs/static
routes enforce local authority/Origin checks. The supported launcher remains
loopback-only. This is not a remotely exposed multi-user deployment or an
authentication system. Retrieved text and synthetic model results remain advisory.

The original Day 1 hours 7–8 mapping and complete two-day schedule are unchanged.
**Stage 7 is Completed. Stage 8 remains Not Started.**

## UI refinement follow-up — 2026-11-08

**Completed — implementation, full regression and browser acceptance verified.**

The user approved the UI plan and explicitly limited application changes to
`api/static/{index.html,styles.css,app.mjs,render.mjs}` and a CSS MIME correction
in `main.py`, with existing tests and relevant documentation allowed. Existing
uncommitted Stage 7 work was retained. No backend business logic, API contracts,
request construction, audit lifecycle, dependencies, migrations or secret settings
were changed. Stage 8 remains Not Started.

### Root cause and changes

The stylesheet returned HTTP 200 with `application/x-css` from the Windows MIME
lookup. Edge explicitly rejected it under strict MIME checking and fell back to
default typography/layout. `main.py` now registers `.css` as `text/css` before
the existing static mount. The running local server was restarted only after
checking that no investigations were active; HTTP verification confirms
`text/css; charset=utf-8`, original CSP and `nosniff`.

The dashboard uses white panels, navy text, blue accents, consistent spacing and
responsive layout. It adds a professional header, category selection, editable
default question, collapsed advanced scope/scenario options, clear primary action,
copyable ID, saved-event badges, executive summary, three historical metric cards,
readable assessments, expandable evidence, modeled statistics/intervals and human
review. Raw JSON presentation was replaced by labeled lists, facts and tables.
The entire original answer remains in a disclosure. Numbers are formatted only;
original precision remains in element titles/data attributes and the audit.

Missing historical rankings and independent design capacity are disclosed rather
than invented. Saved-history dataset names use the existing catalog and status
uses bounded existing GET requests (at most three concurrent). Submission keys,
request construction, HTTP handling, polling, reconciliation and refresh behavior
are preserved; no automatic POST retry or new endpoint was introduced.

### Executed verification so far

- API MIME assertion and existing API/runtime units: **30 passed in 2.35 seconds**.
- `node --test tests/ui/client.test.mjs`: **4 passed**, no failures or skips.
- Final focused Edge desktop/mobile suite: **4 passed in 57.24 seconds**.
- Ruff: **all checks passed**. Compilation and JavaScript syntax checks passed.
- Poetry validation: **All set!** Alembic consistency passed at **0002 (head)**.
- Exact preservation report `data/processed/stage7/ui-after-v1.json`: **all checks
  true**, including all 22 public tables, five audits present at UI-task entry,
  three datasets, 555,714 source records, 2,544 vectors, saved Stage 3 reports,
  original plan, secrets/dependencies and protected backend files. A stricter
  source check allowed only the five approved application paths and found no
  other source/config/report changes. There were zero leftover test schemas.

Browser checks use production-served static MIME/security headers, computed
styles, exact CSS viewports **1440×1200** and **390×1000**, no document overflow,
form labels, visible focus, native Tab/Enter activation, sample button/status
contrast of at least 4.5:1, all question groups/outcomes, saved events, refresh and
reconnect without duplicate POST, evidence expansion and distinct metric values.
Real saved-result checks make GETs only. No paid model request, production
simulation, reseeding or indexing was performed for this UI task.

The original browser window-size flag cropped a wider layout on Windows. The
updated harness uses Edge's debugging protocol through Node's built-in WebSocket
to set/verify the actual viewport and collect console/runtime/resource evidence.
No browser dependency was installed. Initial harness failures exposed inactive
focus emulation, a Windows debugging-file write race, an incomplete Enter key
sequence and a test submission racing initialization. These were corrected in
the test harness, not by changing application lifecycle behavior. The first full
regression run reported **227 passed, 4 failed in 358.84 seconds**, with all four
failures in the then-incomplete keyboard test. That is not a passing full-suite
result; the final corrected full run is recorded below.

The user explicitly declined an extra favicon asset, retaining the file allowlist.
The existing `/favicon.ico` **404 remains** and is reported separately. No CSS,
JavaScript or application runtime errors were observed in the passing browser
checks. The real saved-result browser proxy preserves the actual favicon 404;
it does not mask that exception as successful asset delivery.

Screenshots and JSON browser evidence are under ignored
`data/processed/stage7/ui/`: `actual-saved-1440.png`,
`actual-saved-1440-results.png`, `actual-saved-390.png`,
`actual-saved-390-results.png`, plus controlled-fixture screenshots and reports.
The screenshots were visually inspected; mobile dimensions and reflow were
verified rather than assumed from command-line flags. This is not a full manual
accessibility audit or a new live-model acceptance claim.

### Final UI verification

| Exact command / check | Actual result |
| --- | --- |
| `STAGE2_TEST_POSTGRES=1`, `STAGE7_TEST_SAVED_BROWSER=1`, `UI_SCREENSHOT_DIR=data/processed/stage7/ui`, `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | **231 passed in 360.11 seconds**, exit 0, no skips. Includes all existing regression checks and four explicit-viewport Edge tests. |
| `STAGE7_TEST_SAVED_BROWSER=1`, `.\.venv\Scripts\python.exe -m pytest tests/ui/test_browser.py -q --tb=short` | **4 passed in 57.24 seconds** in the final focused run; the complete suite subsequently passed with extension isolation enabled. |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_api.py tests/unit/test_api_runtime.py -q --tb=short` | **30 passed in 2.35 seconds**. |
| `node --test tests/ui/client.test.mjs` | **4 passed**, no failures/skips. |
| `node --check src/bottleneck_analyzer/api/static/app.mjs`, same for `render.mjs` and `tests/ui/browser-driver.mjs` | **Passed**, exit 0. |
| `.\.venv\Scripts\ruff.exe check . --output-format concise` | **Passed**, all checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests alembic scripts` | **Passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m poetry check` | **Passed**, `All set!`. |
| `.\.venv\Scripts\python.exe -m alembic check` / `current` | **Passed**, no new operations; **0002 (head)**. |
| Live `GET /static/styles.css` on localhost:8000 | HTTP **200**, **text/css; charset=utf-8**, original CSP and `nosniff`. |

An intermediate full run reported **230 passed, 1 failed in 318.18 seconds**:
Edge emitted an isolated-world CSP diagnostic from a pre-installed browser
extension. Browser startup now disables extensions/component background pages.
Diagnostics belonging to extension URLs or their distinct extension-manifest
CSP are retained separately as browser-environment evidence. The application's
served CSP is unchanged; any application CSP violation still fails acceptance.
The final 231-pass run supersedes both earlier failed full runs.

Post-suite preservation was executed again using:

```powershell
.\.venv\Scripts\python.exe scripts/stage7_acceptance.py --before data/processed/stage7/ui-before.json --saved-audit b8291895-7348-429e-b84c-fb33992dea4e --report data/processed/stage7/ui-final-acceptance.json
```

**Passed**, exit 0: all original public-table/audit digests, protected files and
embedding counts match, zero test schemas remain, and PostgreSQL/pgvector health
is healthy. Saved-result status and result return HTTP 200 with the original
46.88 historical JPH, separate 46.25588888888889 simulated mean and six evidence
records. No new investigation record or provider call was created by this check.

The actual saved-result browser reports confirm the exact dimensions
1440×1200 / 390×1000, `overflow: false`, successful native keyboard evidence
activation and empty application error lists. Known favicon and any external
extension diagnostics are separate report fields. Screenshots and JSON evidence
were regenerated by the passing full suite. No manual browser acceptance or paid
LLM execution is implied by these automated checks.

UI-task files changed: `src/bottleneck_analyzer/main.py` (MIME registration only),
the four approved static files, `tests/unit/test_api.py`,
`tests/ui/{test_browser.py,browser-driver.mjs}`, README, this status record and
`docs/design/stage-7-api-ui.md`. No additional application file was introduced.
The exact `client.mjs` request-helper SHA-256 matches the UI entry snapshot.
Other source/configuration/report digests also match outside the five approved
application paths. Existing uncommitted Stage 7 work was not discarded or reset.

Remaining limits: no complete historical ranking or independent design-capacity
value in the unchanged API contract; process-local execution behavior remains;
favicon 404 left unchanged at the user's explicit instruction. No Git commit was
created. **UI refinement is Completed; Stage 8 remains Not Started.**

## Local server network incident — 2026-11-08

The user reported planner failure for investigation
`12441ac6-0bd4-406b-bbd8-4e0e9fbc7a7c`. The saved outcome was `failed`, with
`LLMUnavailable`, before analytics. Provider/model/key presence were configured;
no credential was printed. A model-access GET from the sandbox failed with
Windows `PermissionError`, errno 13 / WinError 10013. The identical authenticated
GET outside the sandbox returned HTTP 200 without generating model output.

The server had been launched in the sandbox, which blocked its outbound model
connection. After verifying no API investigation was active, the agent stopped
that server and relaunched the unchanged supported CLI outside the sandbox,
still on loopback port 8000 with one worker and no reload. No application code,
credential or existing audit record was modified.

A new live API investigation for the user's Constraint question was submitted
once and confirmed as completed:
`cbcd4aa4-1aba-4342-a7da-a1addbeebb18`. HTTP admission was 202; saved planner,
analytics, validation and compose events completed; errors were empty. Polling
after admission measured 42.64 seconds. Actual results were 46.88 historical JPH,
Hemming leading and a 13.119999999999997 JPH design gap (13.12 when displayed).
The new run used the configured real LLM and created its own audit/report; it
performed no simulation or source-data/embedding writes. The older failed audits
remain failed, preserving what actually happened.

The earlier UI-only acceptance deliberately used fixture models and saved results;
this subsequent live operational check verifies model connectivity in the
running server context. Local report:
`data/processed/stage7/network-fix-cbcd4aa4-1aba-4342-a7da-a1addbeebb18.json`.
Users can reopen this completed result or submit a new question. Reconnect does
not rerun an older failed investigation. Stage 8 remains Not Started.


## Evidence-backed chat refinement ? 2026-11-09

Implementation, regression, browser acceptance and final preservation verification
are complete. Stage 8 remains Not Started.

Replaced the dashboard/category/advanced/history presentation with a single
conversation, dataset and UTC-period selectors, visible composer, examples and
New chat. Each answer has View evidence, including the original answer, qualified
source passages, historical measurement references/source samples, simulation
uncertainty and saved workflow checkpoints. Source/model content remains text
only. No metrics are recomputed in the browser and no extra answer model is used.

Added optional previous_investigation_id, a typed bounded conversation summary,
and a five-link read-only audit resolver. Context requires confirmed final IDs,
the same dataset/content version and period; explicit new scope/questions win.
Failed/unsupported/clarification exchanges cannot supply factual answer content.
Refresh restores only the current chat via saved identifiers and GET requests.
New chat clears browser context without deleting audits or cancelling work.
Admission keys, commit gating, polling/reconciliation, final audit confirmation,
loopback/Host/Origin checks, CSP, safe rendering and the CSS MIME fix are retained.

Validation completed so far:

- Existing focused orchestration/API/runtime tests: 77 passed.
- New conversation tests: 11 passed, including five-exchange limit, invalid and
  unconfirmed parents, dataset/version/period isolation, cycles, non-factual
  outcomes, planner handoff and no audit creation for invalid context.
- Updated API unit tests: 21 passed, including provenance bounds/source counts.
- PostgreSQL API/orchestration integration tests: 13 passed in 152.23 seconds,
  using rollback-only isolated schemas, including real prior-audit lookup and
  original-audit preservation.
- Node client tests: 5 passed; import/syntax, request context, GET-only polling,
  all outcomes and scope-reset behavior verified.
- Edge chat fixtures plus actual saved-combined rendering: 4 passed in 53.49
  seconds at 1440?1200 and 390?1000. Verified applied CSS/MIME, no horizontal
  overflow, visible composer, safe source text, genuine persisted progress,
  evidence expansion, five outcomes, lost/truncated acceptance reconciliation,
  follow-up parent, changed-period reset, refresh without duplicate submission,
  and New chat without deleting fixture audits. Reports/screenshots:
  data/processed/stage7/chat/. The prior browser run failed on test-fixture
  behavior (expected injected HTTP error and a premature null DOM lookup);
  both fixtures were corrected before the passing run.
- poetry check via the installed environment: All set!
- Ruff: All checks passed.
- Python compileall of src/tests: passed.
- Alembic current: 0002 (head); alembic check: No new upgrade operations detected.

Separate real-provider acceptance: HTTP 202 admitted
087645f7-04b8-4b93-81e4-28142c392a5e for ?Why is that happening??, linked to the
previous completed constraint investigation cbcd4aa4-1aba-4342-a7da-a1addbeebb18.
It completed the causes route with six source records and no errors; planner,
analytics, knowledge, validation and compose checkpoints all completed. Historical
JPH stayed 46.88 and the cause remained a supported hypothesis. The new run added
its own audit only; it performed no simulation, reseeding or embedding indexing.
Artifacts: data/processed/stage7/chat-live-{accepted,result}.json.

No dependency, migration, queue, service or agent was added. No Git commit created.


Final validation for the chat refinement:

| Command / check | Actual result |
| --- | --- |
| STAGE2_TEST_POSTGRES=1, STAGE7_TEST_SAVED_BROWSER=1; `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | 244 passed in 366.03 seconds. |
| `node --test tests/ui/client.test.mjs` | 6 passed, including the added UTC offset regression. |
| STAGE7_TEST_SAVED_BROWSER=1, UI_SCREENSHOT_DIR=data/processed/stage7/chat; `.\.venv\Scripts\python.exe -m pytest tests/ui/test_browser.py -q --tb=short` | Final 4 passed in 56.81 seconds after the UTC correction; includes contrast, native keyboard and actual saved-result checks. |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_conversation.py -q --tb=short` | Final 11 passed in 1.75 seconds, including exclusion of answer findings from failed/unsupported/clarification context. |
| `.\.venv\Scripts\python.exe -m poetry check` | All set! |
| `.\.venv\Scripts\ruff.exe check .` | All checks passed. |
| `.\.venv\Scripts\python.exe -m compileall -q src tests` and Node syntax checks of app/render/browser-driver | Passed. |
| `.\.venv\Scripts\python.exe -m alembic current` / `alembic check` | 0002 (head); no new upgrade operations. |
| Read-only saved combined API/health acceptance | PostgreSQL/vector healthy; 3 datasets; confirmed result HTTP 200; 46.88 historical JPH and 46.25588888888889 modeled baseline retained; 33 historical references; 6 source passages. |
| Full-row preservation comparison | All original source tables and all nine original audit rows unchanged; 2,544 embeddings unchanged; only the new follow-up audit added; zero remaining test schemas. |
| Protected-file comparison / `git diff --check` | No unexpected source/configuration/report changes; primary plan, .env, dependency files, migrations, analytics/retrieval/simulation and saved Stage 3 reports preserved; no whitespace errors. |

Screenshot review caught offset-bearing database timestamps being sliced as local
wall time in UTC selectors. Dataset dates now normalize through toISOString before
display. The six-test Node run and final four browser checks above ran after that
correction; the full 244-test run preceded that last JavaScript-only correction.
Native Edge screenshots show UTC 00:00 boundaries and a visible composer at both
viewport sizes. Browser application errors are empty; the known favicon 404 is
recorded separately and remains unchanged per the user's file-allowlist decision.

Changed application files for this refinement: existing static index.html,
styles.css, app.mjs, render.mjs and client.mjs; agents/contracts.py and planner.py;
workflows/graph.py; API repository.py and schemas.py. Added workflows/context.py.
Added tests/unit/test_conversation.py; updated unit API, integration orchestration,
Node and Edge tests. Updated README, roadmap, status and Stage 6/7 design docs.
The pre-existing uncommitted Stage 7 changes were preserved.

Limits: context is a bounded summary of five finalized exchanges, not permanent
trusted memory; older visible messages are excluded from planning. Only the
current chat is restored from this browser, with no archived-chat UI. Unknown
admission after process loss cannot be guaranteed or automatically resumed.
Provider outages still report failure honestly. No source data or simulation
values were changed, no dependency added, and no Git commit created.

**Chat refinement Completed. Stage 8 remains Not Started. No implementation blocker remains.**


## Comparison-answer correction ? 2026-11-09 ? Completed

The reported segmentation question had computed comparisons in its result but an
overall-line-only answer. Fixed workflows/validation.py to lead segmentation
answers with stored shift/hour candidate distributions, unresolved groups and
model-specific candidates. The existing API projection now derives the same
summary for older saved results without changing their audits or repeating the
prefix. The chat renders the model comparison table directly beneath the answer;
full comparison/evidence details stay expandable. Model JPH remains qualified as
a contribution to mixed-line output; historical candidates are not proven physical
constraints. No ranking, numerical calculation, routing or source data changed.

Actual verification:

- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_orchestration.py tests/unit/test_api.py tests/unit/test_conversation.py -q --tb=short`: **82 passed in 47.35 seconds**. Added regressions for mixed shift candidates, unresolved/missing segments, model findings, unchanged JPH, and old saved-response projection without audit mutation or duplicate summary prefixes.
- With STAGE2_TEST_POSTGRES=1, `.\.venv\Scripts\python.exe -m pytest tests/integration/test_orchestration.py tests/integration/test_api.py -q --tb=short`: **13 passed in 126.69 seconds**. Existing real graph/API/audit workflows retain behavior in rollback-only PostgreSQL schemas.
- With STAGE7_TEST_SAVED_BROWSER=1 and UI_SCREENSHOT_DIR=data/processed/stage7/comparison-fix, `.\.venv\Scripts\python.exe -m pytest tests/ui/test_browser.py -q --tb=short`: **6 passed in 64.13 seconds**. Fixture chat journeys and actual saved combined/segmentation results at 1440?1200 and 390?1000; model comparison is outside collapsed evidence; safe text rendering, keyboard, contrast, overflow, refresh and admission reconciliation retained.
- `node --test tests/ui/client.test.mjs`: **6 passed**.
- Ruff, compileall, JavaScript syntax and git diff --check: passed.
- Read-only check of the user's saved segmentation audit 6fcec308-833a-4161-9270-464389e95e4a: original full-row fingerprint unchanged; projected answer identifies Hemming across 60 dated shifts and Framing for both SUV and Sedan; original 23.246666666666666 / 23.633333333333333 model JPH contributions preserved.
- Restarted the idle local server and verified HTTP 200 for the corrected saved result. No new investigation, paid model call, simulation, embedding or database write was performed for acceptance. No test schemas remain after the integration run.

This scoped correction ran **101 focused Python checks** plus six Node checks;
the earlier 244-test full regression remains the previous chat-refinement record,
not a claim that the full suite was rerun for this correction. Screenshots and
reports are in ignored data/processed/stage7/comparison-fix/.
Changed application files: workflows/validation.py, api/schemas.py and
api/static/render.mjs. Updated the corresponding unit/Edge tests and Stage 7
design/status/roadmap documentation. No dependency, migration or Git commit added.
Stage 8 remains Not Started. Refresh the current conversation to see the corrected
saved answer; rerunning the investigation is unnecessary.


## Conversational answer correction ? 2026-11-09 ? Completed

Replaced the shared technical-summary presentation with intent-specific ordinary
language in workflows/answers.py. Maintenance answers now lead with what the
linked records suggest and what they do not establish, without unrelated JPH or
design-gap paragraphs or raw labels such as supported_hypothesis. Robot-fault
wording requires actual supporting robot-fault records and maintenance work
orders; a relevant note cannot become an invented component diagnosis. Explicit
maintenance causes, associations, insufficient evidence and unavailable searches
remain distinguishable.

What-if answers lead with the actual intervention and estimated output change,
then explain whether the modeled bottleneck moves and what the confidence
interval means. Repair duration and failure rate remain separate methods.
Constraint/segmentation/combined answers retain their relevant findings and
qualifications. Displayed numbers are readable and rounded; the full-precision
typed tool results, uncertainty, source references and simulations remain intact.
Model-filtered output remains a share of mixed-line output, never an exclusive
capacity claim. Paired statistics and gains are copied, not recalculated by an LLM.

Completed status/copy-ID bookkeeping now lives inside View evidence, leaving
completed answers as conversational paragraphs. Non-success statuses remain
visible. The global synthetic/advisory/human-review notice is unchanged; the full
review notice and durable source citations remain inspectable in evidence.

Both new workflow answers and read-only projections of old saved answers use the
same presenter. No old audit is rewritten and reopening a result makes no model,
simulation or embedding call. Agent 1 still uses its existing grounded-language
interface; no new agent, unconstrained model writer, endpoint, queue, dependency,
ORM change or migration was added. Analytics/retrieval/simulation services,
admission, finalization, safe text rendering and five-exchange context are intact.

Actual validation:

- With STAGE2_TEST_POSTGRES=1, STAGE7_TEST_SAVED_BROWSER=1 and UI_SCREENSHOT_DIR=data/processed/stage7/conversational-fix: `.\.venv\Scripts\python.exe -m pytest -q --tb=short` ? **267 passed in 383.09 seconds**. Includes PostgreSQL integration, all workflow outcomes, and ten Edge journeys across fixture chat and real saved combined/segmentation/maintenance/what-if results at desktop/mobile sizes.
- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_answers.py tests/unit/test_orchestration.py tests/unit/test_api.py tests/unit/test_conversation.py -q --tb=short` ? final **98 passed in 62.38 seconds**. Covers the final maintenance wording/category checks and model-share qualification. Two additional regression cases and their final presentation adjustments were made after the full run collected; they are included in this focused result rather than the earlier 267 count.
- `node --test tests/ui/client.test.mjs` ? **6 passed**.
- Final maintenance-only actual-saved Edge checks: **2 passed in 9.54 seconds**. Verified no generic production boilerplate, metadata inside evidence, visible plain-language answer and no overflow/errors at 1440?1200 and 390?1000.
- Poetry check: All set! Ruff: All checks passed. Python compileall, JavaScript syntax and git diff --check passed.
- Full-row fingerprint comparison: all **15 original audit rows unchanged**, no new public audit created, and zero test schemas left after rollback-only integration checks. This correction performed no public database writes, reseeding, simulation rerun, embedding indexing or paid model call.
- Restarted the idle supported local server and verified HTTP 200 for the existing maintenance and what-if results. Both return the conversational wording without rerunning their investigations.

Application files changed: workflows/validation.py, api/schemas.py and
api/static/render.mjs; added the focused workflows/answers.py presenter. Added
unit answer regressions; updated orchestration/API and Edge assertions to verify
human-friendly wording, evidence boundaries and unchanged calculations. Updated
README, Stage 7 design, roadmap and this status record. Original implementation
plan, dependency configuration and migrations remain unchanged. Screenshots,
example projected answers and preservation reports are ignored artifacts in
data/processed/stage7/conversational-fix/.

No Git commit created. Stage 8 remains Not Started. Refresh the current browser
conversation to use the new display; existing investigations need not be rerun.

Final saved maintenance/what-if browser recapture: **4 passed in 14.97 seconds**
at desktop/mobile sizes after the full regression run; screenshots in the same
conversational-fix artifact directory reflect the final wording.


## Concise evidence presentation ? 2026-11-09 ? Completed

Replaced the large audit-style View evidence contents with the main supporting
facts in ordinary language. Constraint questions show three meaningful station
signals, the recorded output calculation and reference gap, plus a brief caveat.
No raw normalized scores/UUID inventories, repeated answer summaries, saved
workflow checkpoints, irrelevant source/simulation placeholders or long internal
assumption lists appear in the disclosure. Weak or conflicting support remains
qualified. Normalized scores are never relabeled as measured percentages.

Other intents show only relevant evidence: up to three diverse/cited source
excerpts (including a conflicting/excluded record when present), a short paired
simulation comparison with uncertainty, or a few comparison groups with an
optional show-all control. Source excerpts keep original wording, timestamps,
versions and direct/inferred qualifications, with full passage available on
request. Safe text rendering, copy-ID control, visible failure outcomes, answers,
submission/polling/context behavior and all existing security protections remain.
Full technical metadata remains in the unchanged existing API and durable audits.
No backend, data, dependency, migration or agent change was made for this task.

Application files changed: api/static/render.mjs and styles.css. Updated Edge
fixtures/assertions and screenshot capture; added tests/ui/evidence.test.mjs for
plain-language indicator mapping, no invented percentages, source selection,
contradiction preservation, deduplication/version handling and input immutability.
README and Stage 7 design/roadmap/status now describe this concise view.

Executed checks:

- With STAGE7_TEST_SAVED_BROWSER=1 and UI_SCREENSHOT_DIR=data/processed/stage7/concise-evidence: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_api.py tests/unit/test_api_runtime.py tests/ui/test_browser.py -q --tb=short` ? **44 passed in 74.16 seconds**, including twelve Edge fixture/saved-result journeys across desktop and mobile. A Python test-string escape warning seen at collection was subsequently corrected.
- `.\.venv\Scripts\python.exe -W error::SyntaxWarning -m pytest tests/ui/test_browser.py -k constraint_output_loss -q --tb=short` with the same browser flags ? final **2 passed in 15.98 seconds**, no warnings. Actual saved bottleneck evidence contains the key figures, stays below 240 words, and has no visible UUIDs, raw scores or irrelevant sections. Verified desktop 1440?1200 and mobile 390?1000, CSS/MIME, no page overflow, keyboard interaction and no application-console errors.
- `node --test tests/ui/client.test.mjs tests/ui/evidence.test.mjs` ? **12 passed**.
- Ruff, JavaScript syntax, Python compilation and git diff --check passed. Stylesheet still served as text/css; updated renderer HTTP 200 from the running app. A server restart was unnecessary for these static changes.
- Full-row fingerprint comparison ? **all 17 original audits unchanged; count remains 17**. No model/simulation call, embedding write, reseeding or real investigation submission was performed by acceptance.

The full backend regression suite was not repeated for this frontend-only
presentation change; the earlier full-suite results remain historical records.
Screenshots, browser reports and preservation checks are ignored artifacts under
data/processed/stage7/concise-evidence/. In particular,
actual-saved-constraint_output_loss-{1440,390}-evidence.png shows the open concise
View evidence section. No Git commit created. Stage 8 remains Not Started.


## Question-specific composition ? 2026-11-09 ? Completed

Root cause: the planner was restricted to an enumerated prepared introduction,
the workflow appended category text, and the API regenerated category text when
reading the saved answer. The current question and follow-up context therefore
could not control the complete response.

Agent 1 now drafts the full answer using the exact question, scope, qualified
five-exchange context and current validated findings. Its structured output
identifies an answer goal and supporting fact IDs before prose. A focused
agents/composition.py helper supplies the bounded fact catalogue and checks
quantities/units, placeholders, selected source references, simulation intervals
and common unsupported proof claims. One malformed draft can be corrected once;
there is no repeated retry or silent category-summary fallback. Network/provider
errors retain their original failure behavior. Numbers are copied from computed
results, never calculated by the model. These guards do not prove every natural-
language paraphrase; human review and the existing evidence qualifications remain.

The existing Explanation contract adds optional fact_ids and composition_version.
The validated version marker and references are stored in the existing JSONB
audit, without a migration. The renderer preserves the full composed wording, and
the API does not overwrite versioned answers with a template. Legacy saved
responses remain unchanged; new questions must be submitted to obtain the new
composition. No new model/agent, service, endpoint, request field, dependency,
frontend change, workflow route, numerical calculation, source dataset, retrieval
or simulation logic was introduced. The original implementation plan is intact.

Actual validation:

- With STAGE2_TEST_POSTGRES=1, `.\.venv\Scripts\python.exe -m pytest tests/unit/test_composition.py tests/unit/test_orchestration.py tests/unit/test_api.py tests/unit/test_conversation.py tests/integration/test_orchestration.py tests/integration/test_api.py -q --tb=short`: **114 passed in 178.82 seconds**. Covers question-specific answers for identical intents/findings, prior-context delivery, invalid quantities/units/fact/source IDs, bounded correction/failure, overclaim rejection, all graph routes, durable audits, and preservation of the composed wording through PostgreSQL/API round trips. Fixtures are scripted; they are not reported as real-model quality evidence.
- `node --test tests/ui/client.test.mjs tests/ui/evidence.test.mjs`: **12 passed**. The frontend is unchanged.
- Ruff, compileall, Poetry check and git diff --check passed. Original dependency files, ORM/migrations and analytical/retrieval/simulation services were not modified. No temporary PostgreSQL test schemas remain.
- Separate live check with configured **gpt-4o-mini**, using a saved completed baseline investigation as read-only findings: the conclusion question returns Hemming and its **13.12 bodies/hour design-reference gap**; the evidence follow-up instead explains processing/fault occupancy, queue accumulation, upstream blocking/downstream waiting and actual station measurements (including **4.91 vehicles average input queue**). The wording is different and passes the same numerical/reference checks as ordinary execution.
- Early live drafts exposed directly typed figures, mistyped placeholders, unhelpful repetition and an overly strict unused-reference check. Final composition uses an explicit answer goal, observation-first fact ordering, exact computed-value/unit validation and one bounded correction. The accepted live outputs and selected facts are recorded in ignored data/processed/stage7/question-composition/live-composition.json; the verification script performs no database writes.
- The live check preserved all **21 original full audit rows**; audit count stayed 21. No actual investigation, source-data write, simulation rerun or embedding indexing was performed by that acceptance. Restarted the idle local app only after checking no investigation was active; startup and /health HTTP 200 verified. New app process uses the verified composer.

Application scope: agents/planner.py and contracts.py; new agents/composition.py;
workflow graph.py call site and validation.py response rendering; API schemas.py
version guard. Added focused composition tests and updated the existing
orchestration/API fixtures and persistence assertions. Stage 6/7 design and
roadmap/status documentation describe the new behavior. No Git commit created.
Stage 8 remains Not Started. Submit the question again (or a new follow-up) to
see the new answer; refreshing an old saved response does not regenerate it.
