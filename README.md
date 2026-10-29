# SkyMediator — Airline Disruption Recovery Multi-Agent System

**Academic Context:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Team Lead:** Athish Raj (Data & Tools)  
**Team Members:** Dinesh K (Agents & Orchestration), Sanchit Rajesh (Tracing & Evaluation)  
**Instructor:** Dr. Kalyan Nagaraj  

---

## Overview

SkyMediator is an advisory, human-in-the-loop multi-agent decision support system designed to assist airline Operations Control Center (OCC) duty managers during severe airport disruptions (specifically winter fog and AOG events).

### Operating Parameters (Phase 0 Approved)
- **Primary Hub Airport:** Kempegowda International Airport, Bengaluru (**VOBL / BLR**).
- **Secondary / Spoke Airports:** Delhi (VIDP), Mumbai (VABB), Chennai (VOMM), Hyderabad (VOHY), Goa (VOGO), Kolkata (VECC).
- **Fleet:** 15 narrow-body aircraft (Airbus A320 family).
- **Planning Window:** 24-hour tactical horizon.
- **Regulatory Standard:** DGCA CAR Section 7, Series J, Part III (2019 baseline with 2024 toggle).
- **Passenger Care Standard:** DGCA CAR Section 3, Series M, Part IV.
- **Human Authority:** The system is advisory; final recovery plan execution strictly requires Duty Manager approval.

---

## Architectural Principles

1. **Zero LLM Arithmetic:** All duty minutes, connection buffers, slot capacities, costs, and composite scores are computed by deterministic, unit-tested Python functions.
2. **Hard Veto Preservation:** Crew Legality (FDTL) and Slot Agent have absolute veto power. A vetoed plan is strictly barred from surviving candidate pools, regardless of cost.
3. **Bounded Deliberation:** Negotiation is bounded to a maximum of 3 rounds.
4. **Structured Tracing:** Every prediction, proposal, veto, tool call, and score is serialized as a structured `TraceSpan` JSONL record in `traces/`.
5. **Clean-Room Independent Validator:** `skymediator/eval/validator_fdtl.py` provides non-circular regulatory compliance verification.

---

## Project Structure

```
skymediator/
├── AGENTS.md                  # Repository instructions and engineering rules
├── pyproject.toml             # Build configuration and pytest settings
├── requirements.txt           # Locked package dependencies
├── design/                    # 9 Approved Phase 0 design specifications
├── skymediator/
│   ├── config.py              # Pydantic Settings (VOBL hub, 2019 CAR baseline)
│   ├── logging_config.py      # Structured JSONL TraceSpan logging
│   ├── models.py              # Operational models, PlanDiffOp, PlanState
│   ├── db.py                  # SQLite DDL and connection manager
│   ├── fixtures.py            # Seeded synthetic Bengaluru hub fixtures
│   ├── graph.py               # LangGraph StateGraph vertical slice workflow
│   ├── demo.py                # Live end-to-end demonstration script
│   ├── tools/
│   │   ├── schedule.py        # query_schedule, apply_plan_diff, swap_tail
│   │   ├── duty.py            # calc_duty_time (DGCA CAR FDTL calculator)
│   │   ├── slots.py           # check_slot (30-min window capacity & curfews)
│   │   └── scoring.py         # score_plan (normalized penalty function [0, 1])
│   └── eval/
│       └── validator_fdtl.py  # Independent clean-room FDTL validator
├── tests/                     # 21 automated unit and integration tests
└── traces/                    # JSONL execution trace logs per run
```

---

## Quickstart and Verification

### 1. Launch OCC Web Dashboard (Human-in-the-Loop Interface)
```bash
python -m skymediator.app.server
```
Opens the interactive OCC dashboard at `http://localhost:8000`:
- **Real-time Hub Status:** 15 Airbus A320 aircraft, 60 scheduled domestic flights, weather RVR monitoring.
- **Scenario Launcher:** Trigger morning CAT III radiation fog, pilot duty timeout, or outstation AOG.
- **Multi-Agent Deliberation Trace:** Real-time visibility into Rotation proposals, Crew Legality CAR Section 7 citations, and Slot checks.
- **Duty Manager Action Panel:** Inspect trade-offs and submit official approvals or replan requests.

### 2. Run Automated Test Suite
```bash
python -m pytest -v
```
*Current Status: 43 passed in 2.08s (100% test pass rate across data models, tools, schemas, ingestion, scenarios, and web API).*

### 3. Run Ingestion and Scenario Pipelines
```bash
# Ingest weather observations and extract features
python -m ingest.fetch_weather --airport VOBL --seed-db

# Build 60-flight domestic schedule for 15 aircraft
python -m ingest.fetch_schedule --seed-db

# Seed synthetic crew and passenger bookings (reproducible seed=42)
python -m ingest.synth_crew_pax --seed 42

# Seed 10 disruption scenarios (5 standard + 5 adversarial)
python -m ingest.make_scenarios --seed 42

# Build DGCA CAR rules index and 50-item gold evaluation dataset
python -m ingest.build_rules_index
```

### 4. Run Live CLI Demonstration
```bash
python -m skymediator.demo
```
