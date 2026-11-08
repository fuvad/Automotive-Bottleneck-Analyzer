# Implementation Roadmap

Status values used throughout this roadmap:

- **Not started** — no implementation work has been completed or verified.
- **In progress** — implementation is underway and acceptance criteria are not yet complete.
- **Completed** — implementation and the relevant checks have been executed successfully.
- **Blocked** — progress is stopped by a concrete dependency, environment issue, or unresolved requirement; the blocker is recorded.

Stages 1–7 are **Completed**, including Stage 2 final acceptance verified through
Stage 3 output. Stage 7 API/UI, audit admission, persisted-result checks, browser
journeys and preservation are verified. Stage 8 remains **Not Started**.

Implementation completion and final acceptance are tracked separately when an
acceptance criterion needs a later stage's output. A later stage depends on the
completed implementation components it consumes, not on acceptance of its own
future output. Final acceptance is marked Completed only after that output has
been generated and verified.

This roadmap is subordinate to [`implementation-plan.md`](implementation-plan.md). It turns that plan into an execution order without changing its architecture, technical choices, requirements, or two-day schedule.

## 1. Implementation strategy

Build a thin but real vertical slice first. Day 1 should establish the contracts, generate linked synthetic records, run the seven-station SimPy line, calculate historical metrics, retrieve evidence, route all four agents, and expose one complete question-to-answer workflow through the local interface. Each stage should leave a runnable, testable increment rather than a diagram-only placeholder.

Day 2 is reserved for proving and improving that slice: validate conservation, buffers, calendars, seeds, retrieval, scenario uncertainty, and failure handling; improve the weakest measured area; then complete the design package, handoff documentation, demo script, presentation, and rehearsal. Numerical work remains deterministic application code. LLM calls are limited to interpretation, textual evidence interpretation, and explanation, and are always validated before they affect routing or response composition.

Keep the application as a modular monolith. Use the existing package areas under `src/bottleneck_analyzer/`, PostgreSQL with pgvector as the shared store, local mock connectors over synthetic files/database records, SimPy for the real event simulation, LangGraph for controlled routing, FastAPI for the local API, and a lightweight local web UI. Do not expand the system into services or add a new infrastructure dependency during the MVP.

## 2. Development stages

### Stage 1 — Project foundation and configuration

**Status:** Completed

**Objective:** Make the agreed runtime, database, logging, model-provider, embedding, and tracing configuration explicit and testable so later stages can be implemented against stable contracts.

**Dependencies:** Existing starter repository and `AGENTS.md`; no business-domain implementation is required first.

**Components and files:**

- Existing: `pyproject.toml`, `.env.example`, `src/bottleneck_analyzer/core/config.py`, `src/bottleneck_analyzer/core/logging.py`, `src/bottleneck_analyzer/db/base.py`, `src/bottleneck_analyzer/db/session.py`, `alembic.ini`, `alembic/env.py`, `src/bottleneck_analyzer/main.py`, and `tests/unit/test_foundation.py`.
- Proposed, if needed: typed shared contracts under `src/bottleneck_analyzer/domain/`, an initial Alembic revision under `alembic/versions/`, and narrowly scoped configuration/observability tests under `tests/unit/`.

**Important implementation decisions:**

- Keep PostgreSQL plus pgvector; never substitute SQLite or a separate vector database.
- Keep credentials and provider/model names in environment configuration.
- Keep LangSmith tracing optional and ensure a tracing outage does not stop local analytics.
- Define typed request/result and investigation-state contracts before agent logic.

**Concrete tasks:**

1. Inspect the current starter code and preserve working foundation behavior.
2. Confirm Python 3.12+, Poetry, FastAPI, SQLAlchemy 2.x, psycopg, Alembic, SimPy, LangGraph, LangSmith, Pydantic, pytest, and Ruff configuration.
3. Define configuration for database, LLM, embeddings, LangSmith, logging, design rate, actual-output reference, calendar, and feature/runtime switches without hardcoding secrets.
4. Define common status, identifier, unit, scope, question-intent, evidence, scenario, and investigation-state contracts.
5. Make local startup and database/embedding/trace health checks explicit without requiring real plant systems.

**Tests and validation:** Run `poetry check`, foundation pytest tests, import checks, and Ruff. Verify a PostgreSQL psycopg URL is accepted, SQLite is rejected, configuration errors are clear, and tracing can be disabled without breaking local startup.

**Definition of done:** The application imports, settings validate, the database session is configured for PostgreSQL, shared contracts are available to later stages, and the checks above have actually been run.

**Must not be implemented in this stage:** Business analytics, simulation behavior, retrieval ranking, agent prompts, arbitrary SQL tools, production connectors, microservices, Kubernetes, Redis, Celery, SQLite, or a fifth agent.

### Stage 2 — Domain models, database schema, and synthetic data generation

**Status:** Completed — implementation and final acceptance verified.

Implementation detail and reproduction commands: [Stage 2 data model](design/stage-2-data-model.md).
Stage 2's domain contracts, schema, migration, authored-data pipeline, and their
tests are implemented and verified. They satisfy Stage 3's entry dependency.
Stage 3 used those components to generate, validate, load and replay
`sim-30day-baseline-v1`, and independently verified the Framing constraint case in
`sim-framing-validation-v1`. The authored fixture was checked unchanged. These
results close Stage 2's remaining cross-stage acceptance criteria.

**Objective:** Create the common internal model, PostgreSQL schema, provenance relationships, and deterministic 30-day synthetic source history that all later analysis uses.

**Dependencies:** Stage 1 contracts and database configuration.

**Components and files:**

- Existing: `src/bottleneck_analyzer/domain/models.py`, `src/bottleneck_analyzer/domain/enums.py`, `src/bottleneck_analyzer/db/models/__init__.py`, `src/bottleneck_analyzer/data/generators/__init__.py`, `src/bottleneck_analyzer/data/connectors/__init__.py`, `data/raw/`, `data/processed/`, `data/documents/`, and Alembic scaffolding.
- Proposed, consistent with the layout: concrete domain/db model modules under `domain/` and `db/models/`; generator modules under `data/generators/`; read-only source connector and normalization modules under `data/connectors/`; generation/ingestion entry points under `scripts/` or the package; migrations under `alembic/versions/`; fixtures under `tests/fixtures/`.

**Important implementation decisions:**

- Model station, inter-station buffer, vehicle, shift/calendar, MES event, SCADA station-state/fault event, historian reading with quality, CMMS work order, Andon call, shift note, SOP document/section, evidence link, simulation run, and audit/investigation records as related entities.
- Preserve original fields and normalized names/units, source IDs, timestamps, document versions, and provenance.
- Use one fixed generation seed, a synthetic 30-day period, seven stations, SUV/sedan, and two shifts.
- Generate shared events first, then derive related source records; explicitly mark inferred station/time links and include missing notes, irrelevant records, and invalid sensor readings.
- Store embeddings only when retrieval is implemented; the schema must leave room for pgvector beside source metadata.

**Concrete tasks:**

1. Define all seven stations in sequence, including the 60 JPH design reference and approximately 46 JPH recent-output reference as distinct values.
2. Define operating calendar, scheduled hours, planned exclusions, shifts, models, buffers, identifiers, units, and validation constraints.
3. Create SQLAlchemy mappings, foreign keys, indexes, source/provenance fields, audit fields, and a reviewed Alembic migration.
4. Build the deterministic generator and mock connector interfaces for MES, SCADA, historian, CMMS, Andon, shift notes, SOPs, and the later simulation output.
5. Generate a Framing-stronger-constraint expected-results fixture without making it a hardcoded answer in application logic.
6. Add ingestion and normalization checks that reject or label invalid values rather than silently repairing them.

**Tests and validation:** Test model relationships, identifiers, timestamps, units, foreign keys, source preservation, fixed-seed repeatability, 30-day coverage, all seven stations, both models/shifts, invalid sensor quality, irrelevant records, and explicit inferred-link labeling. Use PostgreSQL integration tests where available and isolated generator tests otherwise.

**Definition of done:** A clean local run generates and loads linked synthetic records with reproducible IDs and provenance; the schema migration is reviewable; source-specific records agree with shared incidents; and the expected-results fixture is available for validation.

**Must not be implemented in this stage:** Real PLC/SCADA/MES/CMMS access, machine control, automatic work orders, causal claims, hardcoded bottleneck answers, simulation gain calculations, or unrestricted agent-generated SQL.

### Stage 3 — Seven-station SimPy discrete-event simulation

**Status:** Completed — simulation, experiments, dataset persistence/replay and final verification passed.

The 20-pair 30-day experiment passed the illustrative baseline target: mean
46.255889 JPH, scenario mean 49.609000, paired gain 3.353111 JPH (95% interval
3.275210–3.431012). Hemming remained the candidate after intervention. The
Framing stress case was independently verified and saved. A PostgreSQL disk-space
incident interrupted the first load. After the user freed space and restarted the
service, the full load/replay and authored-fixture value verification passed.
The final suite passed **64 tests**; Alembic reports head `0002` with no schema
differences. See the
[Stage 3 technical document](design/stage-3-simulation.md) for evidence and commands.

**Objective:** Implement a real seven-station flow model that produces the shared synthetic event history and supports reproducible baseline and two intervention methods.

**Dependencies:** Stage 2's completed implementation: domain contracts, schema and
migration, calendar, station/buffer definitions, and source-generation/loading
interfaces. These dependencies are satisfied. Stage 3 does not wait for Stage 2's
final acceptance, because its output supplies the remaining acceptance evidence.

**Components and files:**

- Existing placeholders: `src/bottleneck_analyzer/simulation/config.py`, `vehicle.py`, `station.py`, `buffer.py`, and `engine.py`.
- Proposed, if needed: scenario/result/state-record modules under `simulation/`, source-history adapters under `data/generators/`, and unit/integration tests under `tests/unit/` and `tests/integration/`.

**Important implementation decisions:**

- Simulate Underbody Welding, Framing, Roof Welding, Closures Fitting, Hemming, Sealing, and Final Inspection in order.
- Use finite buffers, SUV/sedan processing distributions, inter-arrival/release sequence, shifts, faults, repairs, blocked/starved/faulted/processing states, work in progress, queue occupancy, and Final Inspection completions.
- Define operating versus calendar fault timing, repair behavior across shift boundaries, interrupted processing, startup/WIP treatment, and equivalent initial conditions.
- Support repair duration ×0.70 and failure rate ×0.70; the primary demonstration is shorter repair duration. Do not sum station gains.
- Use paired baseline/scenario replications, initially 20 where practical, with separate calibration/evaluation seeds.

**Concrete tasks:**

1. Implement entities, station resources, buffers, breakdown/repair processes, shift calendar, and completion collection.
2. Record station-state durations, blocked/starved time, queue occupancy, WIP, faults, repairs, completions, seeds, configuration version, and scenario parameters.
3. Tune the synthetic baseline toward 45–47 JPH, inspect station behavior, and compare with the 60 JPH idealized reference without claiming real-plant validation.
4. Expose a controlled Python simulation interface for the Simulation Agent; an HTTP wrapper is optional only if time remains.
5. Make scenario output report mean gain, variation/uncertainty interval, realized downtime change, and possible new constraint rather than forcing an expected movement.

**Tests and validation:** Test body conservation, finite buffer bounds, blocked/starved transitions, fault interruption/recovery, shift boundaries, repair crossing behavior, seed reproducibility, unchanged non-target stations/parameters, both intervention methods, paired initial conditions, and baseline/scenario result structure.

**Definition of done:** A seven-station SimPy run moves vehicles to Final Inspection, faults propagate through buffers, baseline output is near the illustrative target, both 30% methods execute, and results include uncertainty and state evidence.

**Must not be implemented in this stage:** A capacity-only formula, predetermined bottleneck movement, real equipment API, production change, automatic approval, or claims that calibration proves plant accuracy.

### Stage 4 — Historical analytics and bottleneck candidate identification

**Status:** Completed — persisted historical metrics, segmentation, evidence,
candidate ranking and final 89-test regression suite verified on 2026-11-08.

Implementation and definitions: [Stage 4 analytics](design/stage-4-analytics.md).
The persisted baseline yields 21,096 completions / 450 scheduled hours = 46.88 JPH,
13.12 JPH design gap and Hemming as the observational leader. All 60 dated shifts
lead with Hemming; qualified model proxy rankings differ and are explicitly
limited. The separate Framing dataset ranks Framing despite Hemming having the
most faulted time. Metrics match stored Stage 3 references, including individual
dated shifts and UTC-hour buckets. No calibration was rerun; Stage 3 already
provides it. Existing datasets, schema, dependencies and simulation are unchanged.

**Objective:** Compute deterministic historical metrics and rank constraint candidates while keeping historical associations separate from simulation-based sensitivity conclusions.

**Dependencies:** Stages 1–3; normalized records and simulation-derived history must be available.

**Components and files:**

- Reused: `analytics/__init__.py`, shared domain contracts, existing PostgreSQL
  mappings/configuration/session factory and isolated-schema test infrastructure.
- Created under `src/bottleneck_analyzer/analytics/`: `contracts.py`, `calendar.py`,
  `repository.py`, `candidates.py`, `service.py`, and `cli.py`.
- Created `tests/unit/test_analytics.py`, `tests/integration/test_analytics.py`,
  and `docs/design/stage-4-analytics.md`; README and tracking documents updated.

**Important implementation decisions:**

- Use `JPH = Final Inspection completions / scheduled production hours`, retain unplanned downtime in scheduled hours, and keep design-capacity gap separate from station-specific recoverable loss.
- Calculate effective capacity, processing utilization, downtime contribution, blocked/starved time, queue length where available, model mix, shift, and time-of-day metrics.
- Treat ranking as historical candidate identification only; a weighted score cannot alone establish the line constraint.
- Check units, period boundaries, denominators, missing data, and overlapping state intervals.

**Concrete tasks:**

1. Implement typed analytics inputs/outputs and parameterized read-only data access.
2. Calculate JPH, 60 JPH design gap, station-state metrics, segmentation, and supporting/conflicting evidence IDs.
3. Produce deterministic candidate rankings and a Framing-dominated fixture/case.
4. Define the counterfactual boundary so station-specific recoverable loss is supplied only by simulation.

**Tests and validation:** Use manually checked JPH/design-gap examples; test empty periods, excluded planned breaks, unplanned downtime, overlapping intervals, model/shift denominators, missing data, and deterministic repeated outputs. Confirm historical questions produce figures and source IDs without an LLM.

**Definition of done:** The analytics layer answers constraint/output-loss and shift/model/time questions with reproducible metrics, candidate evidence, warnings, and clear historical-versus-modeled labels.

**Must not be implemented in this stage:** Root-cause conclusions, semantic retrieval, simulation intervention logic, LLM arithmetic, or a claim that the top weighted candidate is proven to be the constraint.

### Stage 5 — Knowledge retrieval and evidence linking

**Status:** Completed — implementation and live semantic acceptance verified;
**17/17 live checks** and final suite **125 passed** on 2026-11-08.

See [Stage 5 retrieval](design/stage-5-retrieval.md). Public retrieval is read-only.
User-authorized enrichment populated 2,544 relevant text records across all seven
stations in the three existing datasets, including 14 SOP sections. All 21 tables'
source facts (excluding only derived embedding fields), dataset hashes and saved
Stage 3 reports matched preservation checks. The configured OpenAI model and live
semantic/hybrid behavior were verified. The distance cutoff was measured and
adjusted to 0.5, with separate held-out positives/negatives. This is synthetic
acceptance evidence, not a general quality guarantee. No migration/dependency was
added; production history, simulation assumptions and analytics are unchanged.

**Objective:** Retrieve relevant maintenance, Andon, shift-note, and SOP evidence with exact links, metadata filters, lexical search, vector similarity, deduplication, and qualified interpretation.

**Dependencies:** Stages 1–4; source records, candidate stations, periods, incident IDs, and metrics must exist.

**Components and files:**

- Reused: retrieval initializer, existing PostgreSQL FTS/pgvector schema, source
  relationships, station vocabulary, Stage 4 result contracts and isolated tests.
- Created under `src/bottleneck_analyzer/retrieval/`: `contracts.py`, `repository.py`,
  `chunking.py`, `embeddings.py`, `indexing.py`, `evidence.py`, `service.py`, `cli.py`.
- Created retrieval unit/integration tests and `docs/design/stage-5-retrieval.md`;
  extended typed embedding settings/template and updated README/tracking documents.

**Important implementation decisions:**

- Retrieve direct incident/work-order links first, then station/time metadata filters, PostgreSQL full-text search, and pgvector similarity.
- Keep short records whole; split long SOPs by section; preserve source IDs, timestamps, station, incident links, document versions, and provenance.
- Treat retrieved text as untrusted data, not instructions. Label findings as recorded maintenance causes, observed associations, supported hypotheses, or insufficient evidence.
- A relevant-sounding note alone does not prove line-level output loss.

**Concrete tasks:**

1. Generate/store embeddings with configurable provider settings and pgvector metadata.
2. Implement exact incident/work-order lookup, lexical search, vector search, filters, result merging, and deduplication.
3. Link candidate metrics to passages and explicitly distinguish direct versus inferred relationships.
4. Add the Knowledge and Root-Cause Agent’s evidence interpretation boundary, keeping numerical findings from Stage 4 authoritative.

**Tests and validation:** Verify Hemming evidence retrieval, exclusion of unrelated incidents, incident/time filtering, duplicate removal, misleading notes, missing sensor data, document-version handling, and evidence ID traceability. Test provider/tracing failure behavior where possible.

**Definition of done:** Given candidate stations and period, retrieval returns linked, traceable passages and a qualified cause assessment with evidence labels and no fabricated source facts.

**Must not be implemented in this stage:** Unfiltered document dumping, causal certainty from text alone, arbitrary external browsing, agent-controlled SQL, or a new vector service.

### Stage 6 — Four-agent implementation and LangGraph orchestration

**Status:** Completed — exactly four agents, controlled LangGraph workflows,
live OpenAI planning/knowledge/combined execution, durable audit and preservation
checks verified on 2026-11-08. Full suite: **192 passed**; final focused checks:
**20 passed**. Stage 7 was ready at that handoff; its completion is recorded below.

See [Stage 6 orchestration](design/stage-6-orchestration.md). Eight live planning
and guard cases passed. The full combined run recomputed 20 paired 30-day
simulations and separate sensitivity checks, preserving 46.88 historical JPH
versus the 46.255889 replication mean. The paired gain was 3.353111 JPH; Hemming
remained the modeled candidate. Four new audit records preserve failed attempts
and the successful investigation. All 20 other business tables, embeddings,
dataset hashes, saved simulation reports and existing service code are unchanged.
No dependency, migration, fifth agent, business endpoint or UI was added.

**Objective:** Connect exactly four logical agents through validated schemas and explicit LangGraph routes so a natural-language investigation completes the historical, cause, simulation, or combined workflow.

**Dependencies:** Stages 1–5; analytics, retrieval, simulation, database, audit, and configuration interfaces must be callable.

**Components and files:**

- Existing: `src/bottleneck_analyzer/agents/__init__.py`, `src/bottleneck_analyzer/workflows/__init__.py`.
- Created: agent contracts, planner, analytics, knowledge and simulation modules;
  workflow graph, shared validation, audit writer and CLI; typed LLM adapter and
  metadata-only observability; unit/integration tests, combined request fixture,
  explicit live acceptance script and Stage 6 technical documentation.

**Important implementation decisions:**

- Preserve exactly four roles: Agent 1 Orchestrator/Planner, Agent 2 Data and Analytics, Agent 3 Knowledge and Root-Cause, and Agent 4 Simulation.
- Validation is shared application code, not a fifth agent. Agent 1 composes the final answer.
- The planner may propose a structured request, but Pydantic validation and a Python router choose only predefined routes; no free-form tool execution or arbitrary SQL.
- Parallelize independent retrieval where safe; run dependent analysis and simulation in order. Persist investigation ID, question, scope, plan, tool results, records, seeds, validation, evidence IDs, model versions, and final response.
- Ask for clarification when “reduce robot-fault downtime by 30%” does not identify repair duration versus failure rate; refuse/qualify unsupported production-change requests.

**Concrete tasks:**

1. Implement all four input/output contracts and investigation state.
2. Implement planner interpretation, scope/intent validation, clarification, and explicit historical/cause/simulation/combined routing.
3. Connect analytics, retrieval, and simulation tools with approved interfaces.
4. Add calculation/unit/evidence/scenario validators and local audit persistence.
5. Add LangSmith spans for planner, tools, retrieval, simulation, and answer composition while tolerating tracing failure.
6. Implement response composition with answer-first metrics, evidence IDs, assumptions, uncertainty, limitations, and human-review notice.

**Tests and validation:** Test all four question groups, ambiguous downtime clarification, unsupported requests, route selection, structured-output validation, tool boundaries, audit completeness, LangSmith-disabled operation, parallel independent work, dependent ordering, and preserved separation of historical findings from simulated predictions.

**Definition of done:** One natural-language combined question travels through all four agents, returns computed and traceable results, persists an audit record, and can also answer each specialist question group with graceful clarification/incomplete responses.

**Must not be implemented in this stage:** An autonomous fifth validator/answer agent, unconstrained agent tools, arbitrary SQL, fabricated evidence, silently selected scenario semantics, automatic plant actions, or a wholesale agent framework beyond the agreed LangGraph orchestration.

### Stage 7 — API and local user interface

**Status:** Completed — the approved evidence-backed chat refinement was verified
on 2026-11-09: 244 pytest tests, six Node tests and four final Edge checks passed.
The UI provides one current conversation, small dataset/UTC-period selectors,
visible composer, View evidence beneath each answer and New chat. Optional
previous_investigation_id resolves at most five finalized exchanges from existing
audits. A bounded historical-provenance projection exposes existing measurements
and source samples. No migration, dependency, queue or additional agent was added.
A real follow-up completed the causes route with six source records; original
source data, 2,544 vectors and all nine pre-existing audit rows were preserved.
This approved refinement supersedes the initial dashboard presentation.
The subsequent comparison-answer correction is also verified: 101 focused Python
checks and six Node checks passed. Shift/model/hour findings now appear in the
answer, with a compact model table, including read-only rendering of old saved
results. Supporting details remain under View evidence; original audits and
analytics calculations are preserved.
The conversational-answer correction is also complete: 267 full-regression checks,
98 final focused Python checks and six Node checks passed. Answers now lead with
intent-specific ordinary language; technical labels and completed bookkeeping
remain under View evidence. Saved audits are projected read-only and unchanged.
The later concise-evidence presentation is verified by 44 API/runtime/browser
checks, twelve Node checks and two final desktop/mobile bottleneck checks.
View evidence now contains only relevant plain-language support and key figures;
full technical records remain in the API/audit. Backend behavior is unchanged.
The subsequent Agent 1 question-specific composition correction is complete:
114 targeted Python/PostgreSQL checks and twelve Node checks passed, plus a live
two-question composition check with the configured model. New answers use the
exact question and qualified follow-up context; checked composed wording survives
audit/API round trips. This supersedes category templates for new investigations,
without changing the four-agent routes, numerical tools or database schema.

See [Stage 7 API/UI](design/stage-7-api-ui.md) and the status execution record.
The existing routing, tool logic and four agents are preserved, with bounded
conversation context added to the planner. Initial audit commit gates
HTTP admission and graph execution; timeout/disconnect cannot release an active
worker's slot. Only persisted events are exposed. Final results require matching
persisted response/audit IDs. Process-local execution, reconnect, uncertainty after
restart and shutdown draining are explicit. Loopback/Host/Origin boundaries,
safe source rendering, bounded projections and sanitized errors are verified.
All original public records, four audits, 2,544 vectors, saved Stage 3 reports and
protected Stage 1–6 source/dependency/migration files match preservation checks.
No new dependency or migration was introduced; Alembic remains `0002`.

**Objective:** Expose the controlled investigation workflow through a lightweight local web application that supports questions, clarification, evidence, simulation comparison, assumptions, uncertainty, and human review.

**Dependencies:** Stage 6 workflow and response contracts; Stage 1 FastAPI entry point.

**Components and files:**

- Existing: `src/bottleneck_analyzer/api/__init__.py`, `src/bottleneck_analyzer/main.py`.
- Proposed: request/response schemas and route modules under `src/bottleneck_analyzer/api/`; local UI templates/static assets or a minimal UI module consistent with the existing FastAPI application; API tests under `tests/`.

**Important implementation decisions:**

- Keep the interface local, read-only, and thin; the workflow remains the source of truth.
- Show answer, key metrics, evidence IDs/passages, simulation baseline/scenario, assumptions, uncertainty, limitations, clarification prompts, and human approval/review before acting.
- Include a saved-output fallback for external model-service interruption; do not expose secrets or unrestricted tools.

**Concrete tasks:**

1. Add an investigation request endpoint and response schema around the controlled workflow.
2. Add question entry, scope/clarification display, expandable evidence, scenario comparison, and audit/review indicators.
3. Run the four example question types from the plan through the interface.
4. Add a concise local startup and clean-start demo path.

**Tests and validation:** Test request validation, response rendering/serialization, clarification, unsupported action requests, evidence IDs, uncertainty fields, model-service outage fallback, and end-to-end API/UI behavior with synthetic data.

**Definition of done:** A production engineer can enter the combined example and see a complete computed, evidence-backed, uncertain, read-only answer through the local interface; all four question groups are demonstrable.

**Must not be implemented in this stage:** PLC controls, production setting changes, real work-order creation, operational approval automation, cloud-only dependency for deterministic analysis, or a large frontend architecture.

### Stage 8 — Testing, validation, documentation, and presentation

**Status:** Not started

**Objective:** Prove the MVP against the implementation plan, resolve the weakest measured issue, document operation and production boundaries, and package/rehearse the required presentation.

**Dependencies:** Stages 1–7 for the full workflow; documentation can begin from verified artifacts but final claims require the completed validation pass.

**Components and files:**

- Existing: `README.md`, `AGENTS.md`, `docs/implementation-plan.md`, `tests/`, `data/`, `alembic/`, and `.env.example`.
- Proposed: updated setup/ingestion/test instructions in `README.md`, design architecture/choices and limitations under `docs/`, demo/presentation materials under `docs/` or the agreed project packaging location, and saved fallback outputs/fixtures in `tests/fixtures/` or `data/processed/`.

**Important implementation decisions:**

- Only report tests and checks that were actually run.
- Preserve local audit records even if LangSmith is unavailable.
- Document edge collection/buffering, on-premise sensitive connectors and analytics, approved cloud LLM/reporting, secure movement, and cloud-outage behavior exactly as agreed.
- Keep human review before operational action and label synthetic data, assumptions, uncertainty, and known limits.

**Concrete tasks:**

1. Run unit, integration, simulation, retrieval, routing, API, pytest, and Ruff checks relevant to the implemented scope.
2. Verify conservation, finite buffers, failures/repairs, calendars, JPH, model/shift/time segmentation, paired seeds, both intervention methods, and uncertainty.
3. Test Framing dominance, irrelevant notes, missing data, ambiguous downtime reduction, unsupported equipment-change requests, and model/cloud outage behavior.
4. Improve the weakest measured area during the designated improvement block without expanding scope.
5. Complete architecture diagram, agent responsibilities/input/output/tool/LLM-code split, state/memory, data/simulation integration, accuracy/security, alternatives, edge/on-premise/cloud placement, outage behavior, guardrails, and human review.
6. Package setup, environment template, schema/data generation/ingestion instructions, SimPy model, test results, known limitations, demo script, presentation, Q&A notes, and clean-start rehearsal.

**Tests and validation:** Use the final checklist below, compare every item to `implementation-plan.md`, execute the clean-start demo, and verify the 20-minute walkthrough plus 10-minute Q&A preparation. Record blockers rather than silently omitting unmet requirements.

**Definition of done:** The prototype, mock data and source files, database instructions, simulation, test results, documentation, saved fallback, presentation, and known limitations are packaged; the end-to-end demo has been rehearsed; every final acceptance criterion is either met or explicitly blocked.

**Must not be implemented in this stage:** New architecture, new infrastructure services, unverified claims, hidden scope expansion, or deletion of tests/requirements to make the status appear complete.

## 3. Dependency order

The critical path is:

```text
Foundation/config
  -> Stage 2 implementation: domain/schema/authored-data pipeline (complete)
  -> Stage 3: SimPy history and scenarios
  -> verify/load the new simulation dataset and close Stage 2 final acceptance
  -> historical analytics
  -> evidence retrieval
  -> four agents + LangGraph
  -> API/local UI
  -> validation, documentation, packaging, presentation
```

The schema and shared contracts must precede code that reads or writes them. The simulation and normalized source history must precede reliable analytics; analytics candidates and incident links must precede focused retrieval; analytics, retrieval, and simulation must all be callable before the combined agent route can be complete; the API/UI must consume the validated workflow rather than duplicate business logic.

There is no circular implementation dependency: Stage 2 implementation enables
Stage 3, and Stage 3 output supplies Stage 2's outstanding acceptance evidence.
Closing that evidence is a verification milestone, not a prerequisite to building
the simulation or a request to repeat completed Stage 2 work.

Work that can run in parallel after its contracts exist includes: database migration work and synthetic generator work; simulation unit tests and source normalization tests; analytics tests and retrieval indexing preparation; independent retrieval and analytics calls within a combined investigation; and documentation of already-verified architecture while Day 2 validation proceeds. Work that must remain sequential includes: domain contracts before schema, schema/data before analytics, candidate scope before targeted evidence retrieval, tool contracts before agent routing, workflow before API/UI, and validation before final claims and presentation.

## 4. Two-day execution mapping

The following mapping preserves every time block in `implementation-plan.md`; it does not create a new schedule.

| Time block from the plan | Roadmap stages and work | Required exit check |
| --- | --- | --- |
| Day 1, hours 0–1 | Stage 1. Set up Python, PostgreSQL/pgvector, LLM/embedding access, LangSmith; define schemas, calendar, metrics, and agent interfaces. | Database, model call, embedding, and trace work. |
| Day 1, hours 1–3.5 | Stages 2–3. Establish domain/schema/data contracts, then implement the minimum SimPy line, fault/repair behavior, finite buffers, and linked mock MES, SCADA, historian, CMMS, Andon, shift-note, and SOP sources. These stages share the block but remain internally ordered. | Bodies flow; faults propagate; source records agree. |
| Day 1, hours 3.5–4.5 | Stage 4. Load/normalize records, calculate JPH, station metrics, and historical candidates, and tune the initial baseline toward 46 JPH. | Historical questions produce deterministic figures and source IDs. |
| Day 1, hours 4.5–5.5 | Stage 5. Index documents with metadata, full-text search, and pgvector. | Related Hemming evidence is retrieved; unrelated incidents are excluded. |
| Day 1, hours 5.5–7 | Stage 6. Connect all four agents through controlled historical, cause, simulation, and combined routes; implement both intervention methods, clarification, validation, audit, and LangSmith spans. | One natural-language question completes the full workflow. |
| Day 1, hours 7–8 | Stage 7. Add the local web interface and run the PDF’s four example question types. | Full computed, traceable demonstration through the interface. |
| Day 2, hours 8–10 | Stage 8 validation. Verify conservation, finite buffers, faults, calendars, and JPH; calibrate/evaluate multiple seeds; run paired scenarios. | Reproducible results with documented model limits and uncertainty. |
| Day 2, hours 10–11.5 | Stage 8 required-question/failure tests. Test the Framing-dominated case, model/shift changes, irrelevant notes, missing data, ambiguous downtime reduction, and equipment-change requests. | Expected outcomes and graceful incomplete responses. |
| Day 2, hours 11.5–12.5 | Stage 8 improvement. Improve the weakest measured area: retrieval, bottleneck evidence, performance, planning, or tracing. | Demonstrated issue resolved without expanding scope. |
| Day 2, hours 12.5–14 | Stage 8 documentation. Complete design documentation, architecture diagram, choices/alternatives, edge/on-premise/cloud placement, outage behavior, guardrails, and human review. | Every PDF design deliverable is covered. |
| Day 2, hours 14–16 | Stage 8 packaging and presentation. Prepare setup/data instructions, demo script, presentation, Q&A, saved fallbacks, and clean-start rehearsal. | Working handoff and 20-minute presentation. |

Stage 8 therefore spans all Day 2 blocks, while Stages 1–7 deliver the Day 1 vertical slice.

## 5. Milestone tracking and acceptance criteria

Update each stage’s `Status` after its work and checks are complete. A stage is **Completed** only when its definition of done and measurable criteria below are satisfied:

Stage 2 was tracked as **Implementation Complete; Final Acceptance Pending Stage 3
Output** until the cross-stage evidence was verified. That acceptance is now
closed. This distinction preserved the criteria without blocking Stage 3 entry.

| Stage | Measurable acceptance criteria |
| --- | --- |
| 1 | `poetry check`, relevant pytest, and Ruff run successfully; settings reject SQLite, accept psycopg PostgreSQL, and expose typed contracts; local tracing is optional. |
| 2 | A fixed-seed run covers 30 days, seven stations, two models, two shifts, all listed source systems, provenance links, invalid/irrelevant fixtures, and a reviewed PostgreSQL/Alembic schema. |
| 3 | SimPy conserves vehicles, respects finite buffers, records all required states, is seed-reproducible, reaches approximately 45–47 JPH for the illustrative baseline, and executes both 30% methods with uncertainty. |
| 4 | JPH, design gap, station metrics, segmentation, candidates, warnings, and source IDs match manually checked fixtures; historical ranking is not presented as proof. |
| 5 | Direct links, lexical retrieval, vector retrieval, metadata filters, deduplication, source/version IDs, and direct/inferred labels work for relevant and misleading records. |
| 6 | Exactly four agents route validated requests; ambiguous scenario language clarifies; combined workflow produces validated evidence-backed output, audit state, seeds, and LangSmith/local traces where available. |
| 7 | The local interface completes the combined example and exposes clarification, evidence, simulation comparison, assumptions, uncertainty, limitations, and human review. |
| 8 | Required tests, documentation, deliverables, fallback outputs, clean-start setup, 20-minute presentation, and 10-minute Q&A preparation are complete or explicitly blocked. |

When blocked, record the specific missing dependency, attempted checks, impact on the two-day scope, and the smallest safe next action. Do not silently downgrade a requirement.

## 6. Engineering rules for Codex

- Inspect existing code before modifying it.
- Implement one stage at a time.
- Do not create placeholder logic just to satisfy an architecture diagram.
- Do not hardcode expected bottleneck results or simulation gains.
- Run relevant tests after each stage.
- Do not claim tests passed unless they were actually executed.
- Update this roadmap’s implementation status after each completed stage.
- Preserve working functionality and avoid unnecessary rewrites.
- Report blockers instead of silently working around important missing requirements.
- Re-read `AGENTS.md` and `docs/implementation-plan.md` before each milestone.
- Keep numerical calculations, routing controls, validation, and source boundaries explicit; do not let an LLM replace deterministic computation or authorize plant actions.

## 7. Final implementation checklist

### Functional workflow

- [x] Local web interface accepts a production-engineer question and returns an answer-first response. Fixture journeys and existing live-combined saved-result rendering verified.
- [x] All four question groups and combined investigation are exposed through the API/UI; browser journeys use controlled fixtures and backend regression retains real computations. No paid/production simulation rerun during Stage 7 is claimed.
- [x] Responses include key metrics, evidence IDs, linked evidence, assumptions, uncertainty, limitations, and human-review guidance.
- [x] Historical findings, recorded causes/associations, supported hypotheses, and simulated predictions are labeled distinctly.
- [x] Investigation ID, question, scope, plan, tool results, records, model/data versions, scenario parameters, seeds, validation, evidence IDs, and final answer are auditable.

### Architecture and agents

- [x] Exactly four logical agents are implemented: Orchestrator/Planner, Data and Analytics, Knowledge and Root-Cause, and Simulation.
- [x] Agent 1 interprets language, validates scope, routes predefined workflows, handles clarification, and composes the final answer.
- [x] Agent 2 uses read-only PostgreSQL and deterministic calculations for JPH, station-state/cycle metrics, candidates, and evidence IDs.
- [x] Agent 3 performs exact incident/work-order, metadata, full-text, and pgvector retrieval and qualifies causes.
- [x] Agent 4 runs approved SimPy baseline/scenario comparisons and reports uncertainty and possible constraint movement.
- [x] LangGraph orchestration uses typed state and explicit routes; validation is shared application code, not a fifth agent.
- [x] LangSmith spans and local logs/audit records work without making tracing a hard dependency. Local logs/audit verified live; optional client paths verified offline, without claiming remote delivery.

### Data and storage

- [ ] PostgreSQL, SQLAlchemy 2.x, Alembic, and pgvector are used; no SQLite or separate vector database is introduced.
- [ ] Synthetic source systems cover MES, SCADA, historian, CMMS, Andon, shift notes, and SOP repository through read-only mock connectors.
- [ ] Related entities cover station, buffer, vehicle, calendar/shift, production event, station-state/fault event, sensor reading/quality, work order, Andon call, shift note, SOP document/section, evidence link, simulation run, and audit/investigation.
- [ ] The generated history is synthetic, fixed-seed, 30 days, seven stations, two models, and two shifts.
- [ ] Shared identifiers link incidents across sources; inferred links are explicitly marked; missing notes, irrelevant records, invalid sensors, document versions, and original/normalized values are preserved.

### Seven-station simulation

- [x] Underbody Welding, Framing, Roof Welding, Closures Fitting, Hemming, Sealing, and Final Inspection are modeled sequentially.
- [x] SimPy includes SUV/sedan processing, finite buffers, WIP, faults, repairs, shifts, processing, blocked, starved, and faulted states, queue occupancy, and completions.
- [x] Operating/calendar fault timing, shift-crossing repairs, interruption/resumption, startup/WIP treatment, and equivalent baseline/scenario conditions are defined.
- [x] Baseline is calibrated toward approximately 46 JPH, initially 45–47 JPH, while preserving the distinct 60 JPH design reference and stating model limits.
- [x] Both intervention methods exist: repair duration ×0.70 and failure rate ×0.70; the primary demonstration uses repair-duration reduction.
- [x] Evaluation uses paired baseline/scenario runs, initially 20 replications where practical, separate seeds, mean gain, variation/uncertainty interval, realized downtime change, and possible new constraint.
- [x] No station gains are summed and no bottleneck movement or gain is predetermined.

### Measurement, retrieval, and validation

- [x] JPH is Final Inspection completions divided by scheduled production hours.
- [x] Unplanned downtime remains in scheduled hours; planned exclusions are explicit; design-capacity gap is separate from recoverable counterfactual loss.
- [ ] Processing, inter-arrival, repair, downtime, blocked, and starved time remain distinct; units, boundaries, denominators, missing data, and overlaps are checked.
- [x] Retrieval uses direct links first, then station/time filters, PostgreSQL full-text search, and pgvector similarity; results merge and deduplicate.
- [x] Evidence includes source IDs, timestamps, stations, incident links, document versions, and direct/inferred relationship labels.
- [ ] Tests cover manual JPH/design gap, conservation, buffers, faults/repairs, shifts, both 30% methods, unchanged non-target parameters, seeds, retrieval relevance/traceability, misleading notes, missing sensors, planner scope, clarification, and unsupported requests.
- [x] Human review is shown before acting on recommendations; no production control or automatic work-order creation exists.

### Documentation and presentation

- [ ] Working prototype, mock-data generator/source files, database setup and ingestion instructions, SimPy model, test results, and known limitations are packaged.
- [ ] Design documentation covers solution overview; why four agents fit; where code is preferable; each agent’s responsibilities, inputs, outputs, tools, LLM/code split, state/memory; orchestration; data and simulation integration; accuracy; security; and alternatives.
- [ ] Architecture diagram covers user, all four agents, data stores, memory/state, all listed plant systems, simulation, and human approval.
- [ ] Production placement explains edge collection/buffering, sensitive on-premise connectors/analytics, approved cloud LLM/reporting, secure movement, cloud-outage local continuation, cloud-feature unavailability, and later synchronization.
- [ ] Presentation is rehearsed for 20 minutes: context 2, architecture/agents 4, data/bottleneck/simulation 4, live demo 7, guardrails/limitations/production path 3, followed by 10 minutes of Q&A.
- [x] Example questions and clearly labeled saved outputs are available as fallback for external model-service interruption.

## Final verification against the implementation plan

Before marking the roadmap complete, compare it line by line with `docs/implementation-plan.md` and verify:

1. Every major requirement appears in a stage, acceptance criterion, schedule exit check, or final checklist.
2. The exact Day 1 and Day 2 time blocks are preserved, including the final two hours for packaging and presentation rehearsal.
3. The four-agent architecture, PostgreSQL/pgvector, SimPy, LangGraph, FastAPI/local UI, synthetic mock connectors, read-only boundary, evidence rules, uncertainty, audit, and human-review decisions are unchanged.
4. The roadmap does not introduce new architectural requirements or remove requirements to simplify implementation.

No requirement was unclear enough to omit. The only paths proposed rather than already present are narrowly scoped modules, migrations, tests, scripts, UI assets, and documentation files within the existing project layout; each is marked as proposed in its stage.
