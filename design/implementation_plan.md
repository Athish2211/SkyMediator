# SkyMediator — Implementation Plan and Task Breakdown

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Milestone Roadmap and Project Timeline

The implementation plan is structured to strictly achieve the BMSCE course milestones:
- **Phase 0 (Current):** Architectural Design Audit, Specification Blueprints & Open Decisions.
- **Milestone 1 — Review 3 (31 October 2026):** **The Smallest End-to-End Vertical Slice (MVS)**. Live demonstration of the core multi-agent loop: Disruption injected -> Rotation proposes plan -> Crew Legality vetos with CAR citation -> Rotation counter-proposes -> Candidate approved.
- **Milestone 2 — Review 4 (07 November 2026):** Full 7-agent system, passenger/cost scoring, LangGraph human interrupt, baselines (Greedy & OR-Tools), evaluation metrics and draft report.
- **Milestone 3 — Final Submission (12 November 2026):** Complete test suite, trace viewer demo, statistical ablation results, and final technical report.

---

## 2. Smallest End-to-End Vertical Slice (MVS)

Before implementing the peripheral agents (Sentinel, Passenger, Cost) or complex baselines, the team will build the **Minimal Vertical Slice (MVS)** to definitively prove the multi-agent architecture:
1. **Scope:** 1 synthetic scenario with 15 aircraft, 1 severe fog disruption window, and 1 illegal crew pairing.
2. **Components:**
   - Ingest & SQLite Database (`skymediator.db`).
   - Deterministic tools: `query_schedule`, `apply_plan_diff`, `swap_tail`, `calc_duty_time`, `retrieve_fdtl`.
   - Core Agents: Rotation Agent (Proposer), Crew Legality Agent (Hard Veto with RAG), Mediator Agent (Coordinator).
   - Minimal LangGraph StateGraph (Propose -> Check Legality -> Veto/Accept -> Recommend).
3. **Proof of Architecture:** When executed, the system must show a trace where:
   - Rotation proposes an aircraft swap that causes an FDTL violation.
   - Crew Legality calls `calc_duty_time`, detects FDP > 12.5 hrs, retrieves CAR Section 7 clause, and issues `VETO`.
   - Mediator receives `VETO`, prompts Rotation for a counter-proposal.
   - Rotation issues a counter-proposal (delaying the flight instead of swapping).
   - Crew Legality validates and issues `PASS`.
   - Mediator marks plan ready for approval.

---

## 3. Work Breakdown Structure (WBS) and Tasks

### Phase 1: Environment & Project Scaffolding

#### Task T-1.1: Environment Setup and Dependency Specification
- **Objective:** Establish reproducible Python environment, locked dependencies, and pre-commit configuration.
- **Dependencies:** None.
- **Expected Files:** `requirements.txt`, `pyproject.toml`, `.gitignore`, `README.md`.
- **Acceptance Criteria:** Clean virtual environment installs without conflicts on Python 3.10+.
- **Verification Command:** `pip install -r requirements.txt && python -c "import langgraph, sqlite3, sklearn; print('OK')"`

---

### Phase 2: Data Ingestion, Synthesis & Database

#### Task T-2.1: Data Feasibility Check (Step 0)
- **Objective:** Verify and document data accessibility for primary Indian hub (DEL) and fallback (ORD).
- **Dependencies:** T-1.1.
- **Expected Files:** `ingest/fetch_weather.py`, `ingest/fetch_schedule.py`, `data/feasibility_note.md`.
- **Acceptance Criteria:** Written confirmation of METAR and schedule data availability.
- **Verification Command:** `python -m ingest.fetch_weather --airport VIDP --check`

#### Task T-2.2: SQLite Database Schema & Migration
- **Objective:** Implement SQLite DDL with relational integrity, foreign keys, and indexes.
- **Dependencies:** T-1.1.
- **Expected Files:** `ingest/schema.sql`, `ingest/db.py`.
- **Acceptance Criteria:** Schema creates all 12 tables; `PRAGMA foreign_key_check` returns 0.
- **Verification Command:** `python -m ingest.db --init && pytest tests/test_db.py`

#### Task T-2.3: Synthetic Crew, Passenger, and Scenario Generators
- **Objective:** Build seeded generators anchoring crew pairings, bookings, connections, and scenarios to real flights.
- **Dependencies:** T-2.2.
- **Expected Files:** `ingest/synth_crew_pax.py`, `ingest/make_scenarios.py`.
- **Acceptance Criteria:** Running generator with `seed=42` produces identical database. 5 standard + 5 adversarial scenarios seeded.
- **Verification Command:** `python -m ingest.make_scenarios --seed 42 && pytest tests/test_synth_data.py`

---

### Phase 3: Deterministic Tools & Independent FDTL Validator

#### Task T-3.1: Schedule and Mutation Tools
- **Objective:** Implement `query_schedule`, `apply_plan_diff`, `swap_tail`, and `check_range_maint`.
- **Dependencies:** T-2.2.
- **Expected Files:** `tools/schedule.py`, `tests/test_schedule.py`.
- **Acceptance Criteria:** `apply_plan_diff` correctly mutates schedules; `swap_tail` enforces `min_turn_min`.
- **Verification Command:** `pytest tests/test_schedule.py`

#### Task T-3.2: FDTL Calculation Engine
- **Objective:** Implement deterministic `calc_duty_time` for DGCA CAR Section 7 Series J Part III.
- **Dependencies:** T-2.2.
- **Expected Files:** `tools/duty.py`, `tests/test_duty.py`.
- **Acceptance Criteria:** Matches all 10 hand-worked CAR duty time and WOCL examples.
- **Verification Command:** `pytest tests/test_duty.py`

#### Task T-3.3: Independent Clean-Room FDTL Validator
- **Objective:** Implement separate, evaluation-only validator in `eval/validator_fdtl.py`.
- **Dependencies:** T-3.2.
- **Expected Files:** `eval/validator_fdtl.py`, `tests/test_validator_fdtl.py`.
- **Acceptance Criteria:** Correctly identifies FDTL violations without importing `tools/duty.py`.
- **Verification Command:** `pytest tests/test_validator_fdtl.py`

#### Task T-3.4: Airport Slots & Curfew Tool
- **Objective:** Implement `check_slot` to detect window movement overflows and curfew breaches.
- **Dependencies:** T-2.2.
- **Expected Files:** `tools/slots.py`, `tests/test_slots.py`.
- **Acceptance Criteria:** Flags movement violations when flights exceed window capacity.
- **Verification Command:** `pytest tests/test_slots.py`

#### Task T-3.5: Passenger Impact & Rebooking Tools
- **Objective:** Implement `get_affected_bookings`, `calc_missed_connections`, and `get_rebooking_options`.
- **Dependencies:** T-2.2.
- **Expected Files:** `tools/passengers.py`, `tests/test_passengers.py`.
- **Acceptance Criteria:** Accurately flags broken connections when inbound arrival delay $> \text{buffer}$.
- **Verification Command:** `pytest tests/test_passengers.py`

#### Task T-3.6: Deterministic Cost Estimation & Scoring Tools
- **Objective:** Implement `estimate_cost` and normalized `score_plan`.
- **Dependencies:** T-2.2.
- **Expected Files:** `tools/cost.py`, `tools/scoring.py`, `tests/test_cost.py`, `tests/test_scoring.py`.
- **Acceptance Criteria:** Prices delays, cancellations, and DGCA mandatory care; normalizes composite score to $[0, 1]$.
- **Verification Command:** `pytest tests/test_cost.py tests/test_scoring.py`

---

### Phase 4: Local RAG Index & Fog Prediction Model

#### Task T-4.1: FDTL Rule Indexing and Agentic RAG Retriever
- **Objective:** Chunk DGCA CAR Section 7 text and build local vector store index.
- **Dependencies:** T-1.1.
- **Expected Files:** `ingest/build_rules_index.py`, `eval/rag_gold.jsonl`.
- **Acceptance Criteria:** Vector store created; query retrieves relevant clause chunks with similarity $> 0.65$.
- **Verification Command:** `python -m ingest.build_rules_index && pytest tests/test_rag.py`

#### Task T-4.2: Sentinel Fog Risk Model
- **Objective:** Train and evaluate scikit-learn classifier on METAR weather observations.
- **Dependencies:** T-2.1.
- **Expected Files:** `agents/sentinel.py`, `tests/test_sentinel.py`.
- **Acceptance Criteria:** Brier score $< 0.20$, outputs probability and lead time.
- **Verification Command:** `pytest tests/test_sentinel.py`

---

### Phase 5: Minimal Vertical Slice (MVS) — Review 3 Target (31 Oct)

#### Task T-5.1: State Definitions & Graph Skeleton
- **Objective:** Define `PlanState`, message schemas, and basic LangGraph node stubs.
- **Dependencies:** T-3.1, T-3.2, T-4.1.
- **Expected Files:** `graph/state.py`, `graph/build_graph.py`.
- **Acceptance Criteria:** Graph compiles, executes stub round, and outputs structured JSONL trace span.
- **Verification Command:** `python -m graph.build_graph --dry-run`

#### Task T-5.2: Core Veto Loop (Rotation, Crew Legality, Mediator)
- **Objective:** Integrate real Rotation, Crew Legality (with RAG), and Mediator agents into the loop.
- **Dependencies:** T-5.1.
- **Expected Files:** `agents/rotation.py`, `agents/crew.py`, `agents/mediator.py`.
- **Acceptance Criteria:** End-to-end execution shows: Proposal -> Illegal FDTL Veto with clause citation -> Counter-proposal -> Pass.
- **Verification Command:** `python -m app.cli --scenario SCENARIO_FOG_01 --smoke-test`

---

### Phase 6: Full Multi-Agent Graph & Human Interrupt

#### Task T-6.1: Slot, Passenger, and Cost Agents Integration
- **Objective:** Integrate Slot Agent (hard veto), Passenger Agent (scoring), and Cost Agent (pricing).
- **Dependencies:** T-3.4, T-3.5, T-3.6, T-5.2.
- **Expected Files:** `agents/slot.py`, `agents/passenger.py`, `agents/cost.py`.
- **Acceptance Criteria:** All agents execute in parallel; Mediator ranks surviving plans with normalized scoring.
- **Verification Command:** `pytest tests/test_multi_agent.py`

#### Task T-6.2: LangGraph Human-in-the-Loop Interrupt
- **Objective:** Implement `interrupt()` pause for human duty manager approval.
- **Dependencies:** T-6.1.
- **Expected Files:** `graph/build_graph.py`, `app/cli.py`.
- **Acceptance Criteria:** Graph execution pauses; CLI prompts duty manager; resumes on input.
- **Verification Command:** `python -m app.cli --scenario SCENARIO_FOG_01 --interactive`

---

### Phase 7: Optimization Baselines & Adapters

#### Task T-7.1: Greedy Baseline Heuristic
- **Objective:** Implement rule-based recovery baseline.
- **Dependencies:** T-3.1, T-3.6.
- **Expected Files:** `eval/baselines/greedy_recovery.py`.
- **Acceptance Criteria:** Deterministically resolves disruptions using simple heuristic rules.
- **Verification Command:** `python -m eval.baselines.greedy_recovery --scenario SCENARIO_FOG_01`

#### Task T-7.2: OR-Tools Optimization Solver
- **Objective:** Formulate and solve MIP / CP-SAT disruption recovery model in Google OR-Tools.
- **Dependencies:** T-3.1, T-3.6.
- **Expected Files:** `eval/baselines/or_tools_solver.py`.
- **Acceptance Criteria:** Finds provably optimal cost for candidate schedule disruptions.
- **Verification Command:** `python -m eval.baselines.or_tools_solver --scenario SCENARIO_FOG_01`

#### Task T-7.3: ROADEF 2009 Benchmark Adapter
- **Objective:** Ingest and adapt ROADEF 2009 Challenge problem instances.
- **Dependencies:** T-7.1.
- **Expected Files:** `eval/baselines/roadef_adapter.py`.
- **Acceptance Criteria:** Loads ROADEF instance into SkyMediator state format.
- **Verification Command:** `python -m eval.baselines.roadef_adapter --test`

---

### Phase 8: Evaluation Harness & Reports (Review 4 & Final)

#### Task T-8.1: Evaluation Harness Execution
- **Objective:** Run SkyMediator, Greedy, and OR-Tools across 25 scenarios with 10 repeated seeds.
- **Dependencies:** T-6.2, T-7.1, T-7.2.
- **Expected Files:** `eval/run_eval.py`, `eval/metrics.py`.
- **Acceptance Criteria:** Generates comprehensive metrics table and `results.json`.
- **Verification Command:** `python -m eval.run_eval --all --repeats 10`

#### Task T-8.2: Statistical Significance & Ablation Report
- **Objective:** Compute paired Wilcoxon tests, bootstrap CIs, and generate final tables/plots.
- **Dependencies:** T-8.1.
- **Expected Files:** `eval/generate_report.py`, `docs/final_evaluation_report.md`.
- **Acceptance Criteria:** Full academic report with statistical verification and ablation figures.
- **Verification Command:** `python -m eval.generate_report`
