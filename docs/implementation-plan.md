# Bottleneck Analysis Prototype — Two-Day MVP Implementation Plan

## Purpose and scope

Build a working, evidence-backed prototype for the automotive body-shop exercise. A production engineer should be able to ask which station limits jobs per hour (JPH), how much output is lost, whether the constraint varies by shift, vehicle mix, or time of day, what causes the loss, and what a 30% reduction in robot-fault downtime would change. The line has two models (SUV and sedan), two shifts, and seven sequential stations:

1. Underbody Welding
2. Framing
3. Roof Welding
4. Closures Fitting
5. Hemming
6. Sealing
7. Final Inspection

The design rate is 60 JPH; the stated recent actual average is approximately 46 JPH. These are distinct references. All prototype plant records are synthetic. The real plant systems and simulation API are unavailable, so local mock connectors and a working SimPy discrete-event simulation represent them. The prototype is an advisory, read-only application; production equipment changes and operational approvals remain with plant personnel.

Build a complete vertical workflow on Day 1, then spend Day 2 validating, improving, documenting, and rehearsing it. Aim for two focused eight-hour days, with the last two hours reserved for packaging and presentation rehearsal.

## Definition of an end-to-end MVP

From the user interface, an engineer can ask, for example: “Which station limits JPH, what is causing the loss, and what happens if its robot-fault repair duration is reduced by 30%?” The application interprets the question, computes historical metrics, retrieves linked textual evidence, runs baseline and scenario simulations, checks its claims, and displays an answer with evidence IDs, assumptions, and uncertainty. It also supports the four question groups in the exercise: constraint and output loss; segmentation by shift/model/time; causes; and the 30% what-if with potential constraint movement.

One Python application, one PostgreSQL database with pgvector, and one SimPy simulation module are sufficient for the prototype. The local simulator has a controlled Python tool interface standing in for the plant's simulation API; an HTTP wrapper can be added if time remains.

## Architecture and four agents

```text
Production engineer / local web interface
               |
Agent 1: Orchestrator / Planner
  LLM interpretation -> validated request -> Python workflow router
               |
       +-------+----------------+------------------+
       |                        |                  |
Agent 2: Data and       Agent 3: Knowledge    Agent 4: Simulation
Analytics Agent         and Root-Cause Agent  Agent
SQL + deterministic     linked records +      scenario validation +
calculations            hybrid retrieval       SimPy execution
       |                        |                  |
       +------------------------+------------------+
               |
    Shared validation functions
               |
 Agent 1 composes evidence-backed answer
```

| Agent | Inputs | Outputs | Tools and implementation boundary |
| --- | --- | --- | --- |
| 1. Orchestrator / Planner | User question, session context | Validated intent and scope, workflow state, final answer or clarification | LLM interprets language and explains validated findings; Python schema and router choose and control permitted workflows. |
| 2. Data and Analytics Agent | Time range, model, shift, station scope | JPH, station-state and cycle metrics, historical constraint candidates, evidence IDs | Read-only PostgreSQL queries and deterministic Python calculations. |
| 3. Knowledge and Root-Cause Agent | Candidate stations, incidents, period, fault categories | Retrieved passages, linked maintenance and operator evidence, qualified cause assessment | PostgreSQL full-text search, pgvector, metadata filters, incident links; LLM interprets relevant text. |
| 4. Simulation Agent | Baseline configuration, validated change method and amount | Baseline/scenario JPH, uncertainty, station-state changes, possible constraint movement | SimPy and deterministic scenario setup, execution, and comparison. |

Validation is shared application code rather than a fifth agent. Agent 1 composes the final response. Independent retrieval can run in parallel; dependent analysis and simulation steps run in order. The planner may propose a structured request, but the Python router selects from predefined historical, cause, simulation, and combined workflows.

Each investigation keeps temporary state: investigation ID, question, scope, plan, tool results, retrieved records, simulation parameters and seeds, validation status, and evidence IDs. Persist the audit record and approved model configurations in PostgreSQL. Follow-up questions may reuse the current session's scope; generated hypotheses do not become trusted long-term plant facts.

## Technology and storage decisions

| Area | Choice | Reason and considered alternative |
| --- | --- | --- |
| Application and controlled orchestration | Python with typed request/result schemas and explicit workflow routing | Easy to inspect and test. A larger agent framework is an alternative if workflow complexity grows. |
| LLM | Configurable enterprise-approved model | Used for question interpretation, textual synthesis, and answer wording; core calculations remain in code. |
| Operational, document, and audit data | PostgreSQL | One shared store for structured records, document text/metadata, evidence links, investigations, and results. SQLite was considered for easier startup. |
| Semantic retrieval | pgvector in PostgreSQL | Similarity search beside source metadata and relational joins; no separate vector database. |
| Exact and lexical retrieval | Identifier joins, metadata filters, PostgreSQL full-text search | Exact fault IDs and station names require precise matching. Combine with vector retrieval for wording differences. |
| Original documents and exports | Local files referenced from PostgreSQL | Preserve originals and provenance. Object storage is a production alternative. |
| Simulation | SimPy | Models entities, stations, finite buffers, breakdowns, repairs, and schedules; a capacity-only formula would miss line interactions. |
| Observability | LangSmith traces plus local logs and PostgreSQL audit records | Trace planner, tools, retrieval, simulation, and response; keep durable evidence and operational diagnostics locally. Tracing failure must not stop local analytics. |
| Interface | Lightweight local web application | Question entry, clarification, answer, expandable evidence, simulation comparison, and assumptions. |

The production design must explain read-only connectors to PLC/SCADA, MES, historian, CMMS, Andon, shift notes, SOP repository, and the plant simulation API. The prototype connectors read synthetic CSV, JSON, text, and database records through the same logical interfaces. Direct PLC control, production setting changes, and automatic work-order creation are outside the advisory workflow.

## Measurement and evidence rules

Define metrics before generating data:

```text
JPH = bodies completed at Final Inspection / scheduled production hours
Design-capacity gap = 60 JPH - observed JPH
Scenario gain = scenario JPH - baseline JPH
```

The operating calendar explicitly records scheduled shift windows and any excluded planned breaks or maintenance. Unplanned downtime remains in scheduled hours. The design-capacity gap is not the loss attributable to one station. A station-specific recoverable loss requires a defined counterfactual simulation; individual station gains must not be summed because effects can overlap.

Keep processing time, inter-arrival time, repair time, downtime, blocked time, and starved time distinct. Check units, period boundaries, model/shift denominators, missing data, and overlapping station-state intervals. Distinguish original source facts, normalized fields, inferred record links, historical associations, and simulated predictions in the final answer.

## Synthetic data and common internal model

Define related entities rather than forcing every source into one generic event row: station (sequence and planned cycle time), inter-station buffer (capacity), vehicle (model and release sequence), shift/calendar, MES production event, SCADA station-state interval and fault event, historian sensor reading with quality flag, CMMS work order, Andon call, shift note, SOP document/section, evidence link, and simulation run. Use common station, vehicle, fault-event, work-order, and timestamp identifiers where they exist. Preserve original fields alongside normalized names and units.

Create a shared synthetic event history from the simulation and derive source-specific records from it. One Hemming robot fault can generate a SCADA fault interval, delayed MES movements, historian readings, an associated CMMS work order, an Andon observation, and a shift note. Some incidents can lack human notes; include irrelevant records and invalid sensor readings to test retrieval and validation. SOPs are separately authored sample procedures with versions and source IDs. Link records by shared IDs where possible; explicitly mark any station/time-based inferred link.

The intended dataset covers seven stations, two models, two shifts, and a synthetic 30-day period. Use a fixed generation seed and keep an expected-results fixture, including a case where Framing is the stronger constraint. Synthetic sensor patterns illustrate analytical use; they do not establish real physical causation.

## Historical bottleneck analysis and simulation

Stage A ranks historical **candidates** using effective capacity, processing utilization, downtime contribution, blocked time, starved time, and queue length where available. Show supporting and conflicting evidence. A weighted score may organize candidates but cannot alone determine the line constraint.

Stage B uses the seven-station discrete-event model to test line throughput sensitivity. Simulate bodies moving through finite buffers with model-specific processing times, faults, repairs, shift schedules, and completion at Final Inspection. A Hemming fault can fill its upstream buffer and block earlier stations; after repair the flow resumes. Record state durations, queue occupancy, work in progress, completions, and JPH. Define whether faults arise in operating or calendar time, whether repairs cross shift boundaries, and how interrupted processing resumes.

Calibrate the baseline to approximately 46 JPH, initially targeting 45–47 JPH, and inspect station behavior as well as total output. Compare an idealized low-loss case with the 60 JPH design reference and explain any mismatch. Use separate seeds for calibration and evaluation, equivalent initial conditions for baseline and scenarios, and explicit startup/work-in-progress treatment. Matching the exercise's 46 JPH reference is consistency with an illustrative target, not proof of accuracy against real plant data.

Support two defined robot-fault scenarios: reduce **repair duration** by 30% (targeted repair durations multiplied by 0.70), or reduce **failure rate** by 30% (targeted failure rate multiplied by 0.70). The primary demonstration uses the repair-duration scenario. If a question says only “reduce robot-fault downtime by 30%,” Agent 1 requests clarification of the method. Record target station, category, method, percentage, baseline version, calendar, and seeds. Run repeated paired baseline/scenario experiments where practical, initially 20 replications, and report mean gain, variation or an uncertainty interval, realized downtime change, and any new modeled constraint. The model must report what it computes rather than force a predetermined bottleneck move.

## Retrieval and root-cause analysis

Store maintenance descriptions, Andon remarks, shift notes, and SOP sections with source IDs, timestamps, station, incident links, and document versions. Short records remain whole; split long SOPs by section. Generate embeddings for chunks and store them in pgvector.

Retrieve direct incident/work-order links first, then apply station and time metadata filters, PostgreSQL full-text search, and vector similarity. Merge and deduplicate results. Agent 3 combines these passages with Agent 2's metrics and labels findings as recorded maintenance causes, observed associations, supported hypotheses, or insufficient evidence. A relevant-sounding note alone does not prove line-level output loss.

## Two-day execution schedule

| Time | Build activity | Exit check |
| --- | --- | --- |
| Day 1, hours 0–1 | Set up Python, PostgreSQL/pgvector, LLM/embedding access, LangSmith; define schemas, calendar, metrics, and agent interfaces. | Database, model call, embedding, and trace work. |
| Day 1, hours 1–3.5 | Implement minimum SimPy line, fault/repair and finite buffers; generate linked mock MES, SCADA, historian, CMMS, Andon, shift-note, and SOP sources. | Bodies flow; faults propagate; source records agree. |
| Day 1, hours 3.5–4.5 | Load and normalize data; calculate JPH, station metrics, and historical candidates; tune initial baseline toward 46 JPH. | Historical questions produce deterministic figures and source IDs. |
| Day 1, hours 4.5–5.5 | Index documents with metadata, full-text search, and pgvector. | Related Hemming evidence is retrieved; unrelated incidents are excluded. |
| Day 1, hours 5.5–7 | Connect all four agents through controlled historical, cause, simulation, and combined routes; implement both intervention methods, clarification, validation, audit, and LangSmith spans. | One natural-language question completes the full workflow. |
| Day 1, hours 7–8 | Add the local web interface and run the PDF's four example question types. | Full computed, traceable demonstration through the interface. |
| Day 2, hours 8–10 | Verify conservation, finite buffers, faults, calendars, and JPH; calibrate and evaluate multiple seeds; run paired scenarios. | Reproducible results with documented model limits and uncertainty. |
| Day 2, hours 10–11.5 | Test required questions and failures: Framing-dominated case, model/shift changes, irrelevant notes, missing data, ambiguous downtime reduction, and equipment-change requests. | Expected outcomes and graceful incomplete responses. |
| Day 2, hours 11.5–12.5 | Improve the weakest measured area: retrieval, bottleneck evidence, performance, planning, or tracing. | Demonstrated issue resolved without expanding scope. |
| Day 2, hours 12.5–14 | Complete design documentation, architecture diagram, choices/alternatives, edge/on-premise/cloud placement, outage behavior, guardrails, and human review. | Every PDF design deliverable is covered. |
| Day 2, hours 14–16 | Package setup steps, environment template, data-generation and ingestion instructions, demo script, presentation, and Q&A; rehearse from a clean start. | Working handoff and 20-minute presentation. |

## Testing, validation, and final answer format

Use small manually checked examples for JPH and design gap. Test body conservation, buffer bounds, fault interruption/recovery, shift boundaries, both 30% scenario methods, and unchanged non-targeted parameters. Compare the baseline over evaluation seeds. Verify retrieval by incident IDs and time, including misleading notes and missing sensor data. Test the planner's intent, scope, clarification, and unsupported requests.

Before response composition, verify calculations, units, period and denominator, cited evidence IDs, scenario parameters, and separation of historical findings from simulation outcomes. Responses should lead with the answer and show key metrics, linked evidence, likely explanations, simulation results when applicable, assumptions, uncertainty, and limitations. Preserve a local audit record of question, route, tool results, data/model versions, simulation seeds, and final answer; LangSmith traces show execution timing and agent/tool steps. Human review is shown before acting on recommendations.

## Submission and presentation deliverables

Provide the working prototype, mock data generator and source files, database setup/ingestion instructions, SimPy model, test results, and known limitations. The design package must cover solution overview; why four agents fit and where code is preferable; each agent's responsibilities, inputs, outputs, tools, LLM/code split, state and memory; orchestration; data and simulation integration; accuracy and security; and a complete architecture diagram covering user, agents, data stores, memory, all listed plant systems, simulation, and human approval.

The production diagram places collection and buffering at the edge, sensitive connectors and analytics on-premise, and any approved LLM or centralized reporting service in the cloud. Explain secure movement between tiers and behavior during a cloud outage: local collection and deterministic analysis continue where deployed; cloud-dependent language features report unavailability; queued data synchronizes later.

Prepare a 20-minute walkthrough: problem/context (2 minutes), architecture and agents (4), data/bottleneck/simulation method (4), live demonstration (7), guardrails/limitations/production path (3), followed by 10 minutes of Q&A. Rehearse with example questions and clearly labeled saved outputs as a fallback for external model-service interruption.

## Project reference

Use this document as the primary project reference when creating `AGENTS.md` and the initial folder structure. Those later artifacts should preserve the four-agent design, PostgreSQL/pgvector, SimPy event simulation, linked synthetic source systems, and the two-day MVP sequence described here.
