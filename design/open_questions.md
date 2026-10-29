# SkyMediator — Open Questions, Decisions, and Design Proposals

**Document Version:** 1.0.0  
**Status:** Pending User Approval  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Executive Summary

This document consolidates all open questions from the initial specification (`design_document-1.pdf`, Section 12) along with material architectural design proposals derived from the Phase 0 audit. 

**CRITICAL CONSTRAINT:** In accordance with the project instructions, **no application code or dependencies will be installed until the User approves the decisions in this document.**

---

## 2. Core Operational and Engineering Decisions

### Decision 1: Hub Airport and Flight Data Strategy
- **Context:** The intended setting is an Indian airport subject to severe winter fog (e.g., Indira Gandhi International Airport, Delhi - DEL / VIDP; Winter December 2023 – January 2024). However, public DGCA schedule files are typically aggregate tables or non-machine-readable PDFs without individual aircraft tail numbers.
- **Options:**
  - **Option A (Recommended - Hybrid Indian Hub):** Use Delhi (DEL) as the hub. Download real METAR weather from IEM/NCEI for VIDP. Use published seasonal flight schedules from DGCA/FlightRadar24 to construct 60 scheduled flights, and synthetically assign tails and rotations with fixed seeds. Fallback to BTS only if schedule construction fails.
  - **Option B (US BTS Fallback):** Switch the hub to Chicago O'Hare (ORD) or Atlanta (ATL) using US BTS on-time performance data, but evaluate under DGCA rules as an academic hybrid.
- **Decision Needed From User:** Choose Option A (DEL hybrid) or Option B (US BTS).

---

### Decision 2: Regulatory Baseline (DGCA CAR FDTL Version)
- **Context:** DGCA CAR Section 7, Series J, Part III had new revised norms published in January 2024 (mandating 48-hour weekly rest, stricter night duty limits, and definition of night duty starting earlier), but the implementation was formally deferred following airline representation.
- **Options:**
  - **Option A (Recommended):** Implement the **2019 baseline regulation** (the active, legally enforceable rules in airline OCCs today), with a configurable software toggle to evaluate the 2024 deferred rules in ablation experiments.
  - **Option B:** Implement exclusively the 2024 revised norms.
- **Decision Needed From User:** Confirm Option A (2019 baseline with 2024 toggle) or Option B.

---

### Decision 3: LLM and Embedding Model Stack
- **Context:** The system requires a language model for agent reasoning (semantic analysis, counter-proposal drafting, RAG self-reflection) and an embedding model for vector retrieval of CAR clauses.
- **Options:**
  - **Option A (Free-Tier Cloud API - Highest Quality):** Google Gemini 1.5 Flash (via free API tier) or Groq (Llama-3-70B/8B free tier) for LLM reasoning, paired with `sentence-transformers/all-MiniLM-L6-v2` locally for embeddings.
  - **Option B (100% Local Offline):** Ollama running `llama3:8b` or `qwen2.5:7b` locally, paired with `all-MiniLM-L6-v2` locally.
- **Decision Needed From User:** Choose Option A (Gemini 1.5 Flash / Groq) or Option B (Local Ollama).

---

### Decision 4: User Interface and Demonstration Mode
- **Context:** For Review 3 (31 October) and Review 4 (7 November), the project requires a demonstration interface for the Human Duty Manager to review candidate plans and approve the final recommendation.
- **Options:**
  - **Option A (Recommended):** Rich Terminal CLI (using `rich` formatting) for the core loop + interactive human interrupt prompt, paired with an offline JSONL Trace Viewer script (`app/trace_viewer.py`) that exports visual HTML/markdown reports.
  - **Option B (Web Dashboard):** Build a lightweight Streamlit or FastAPI + vanilla CSS web dashboard displaying the live LangGraph state and approval buttons.
- **Decision Needed From User:** Choose Option A (CLI + Trace Viewer) or Option B (Streamlit/FastAPI Web Dashboard).

---

### Decision 5: ROADEF 2009 Integration Scope
- **Context:** ROADEF 2009 Challenge (Amadeus) is a benchmark for aircraft rotation recovery and passenger disruption. However, the exact challenge dataset contains specific French/European airline constraints that may require significant adapter logic.
- **Options:**
  - **Option A (Recommended):** Prioritize the 25 custom synthetic/replay scenarios (10 standard, 10 stress, 5 adversarial) for primary evaluation. Build a scoped ROADEF adapter (`eval/baselines/roadef_adapter.py`) for a subset (Instance A01-A05) to compare against published solver scores.
  - **Option B:** Make full ROADEF challenge replication the primary benchmark.
- **Decision Needed From User:** Approve Option A (Custom Suite primary + ROADEF subset).

---

### Decision 6: Team Lead and Responsibility Alignment
- **Context:** The project has three student owners (Athish Raj, Dinesh K, Sanchit Rajesh). The specification document noted: "Who is team lead."
- **Current Assignment in Document:**
  - **Athish Raj:** Data ingestion, synthetic generation, SQLite schema, deterministic tools.
  - **Dinesh K:** Multi-agent development, prompts, LangGraph orchestration, human interrupt.
  - **Sanchit Rajesh:** Tracing, observability, evaluation harness, baselines, statistical analysis.
- **Decision Needed From User:** Confirm the Team Lead among Athish, Dinesh, or Sanchit.

---

## 3. Material Design Changes Requiring Explicit Approval

The following architectural modifications are proposed to resolve the contradictions identified in Step 2:

| Proposal ID | Proposed Modification | Rationale / Benefit | Risk / Alternative |
| :--- | :--- | :--- | :--- |
| **PROP-01** | **Add `apply_plan_diff` Tool:** Introduce a pure deterministic function that applies atomic `PlanDiffOp` mutations to flight schedules in memory before validation. | Resolves **GAP-01**. Prevents string-based plan mutations and guarantees deterministic schedule simulation. | Without it, agents must formulate entire schedules, which risks massive hallucinations. |
| **PROP-02** | **Normalized Penalty Score:** Implement a bounded penalty function $[0, 1]$ where delay, missed passengers, cost, and crew penalties are scaled to comparable ranges. | Resolves **GAP-06**. Prevents financial cost ($10^5$) from mathematically obliterating delay minutes ($10^2$). | Unnormalized score results in cost dominating all decisions. |
| **PROP-03** | **Relational Normalization of Crew Duties:** Split `crew_pairings` into `crew_members`, `crew_duties`, and a junction table `crew_duty_flights`. | Resolves **GAP-05**. Eliminates unnormalized comma-separated lists, allowing standard SQL queries and foreign keys. | Non-normalized design causes parsing overhead and data inconsistency. |
| **PROP-04** | **Rejection Handling at Interrupt:** When the Duty Manager rejects a plan during the LangGraph `interrupt()`, allow the manager to inject constraints (e.g. "do not cancel flight 102") and trigger one additional deliberation round. | Resolves **GAP-09**. Prevents system from crashing or dead-ending upon human rejection. | Hard exit without replan requires complete system restart. |
| **PROP-05** | **Mediator Reflection Scope Clarification:** Explicitly prohibit the Mediator from calling `validate_plan_independent`. Restrict Mediator reflection to multi-objective trade-offs and agent consensus. | Resolves **GAP-03**. Preserves clean-room independence of the evaluation validator. | Calling independent validator at runtime makes evaluation circular. |
