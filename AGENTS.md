# SkyMediator — Repository Instructions and Operational Guidelines

**Project:** SkyMediator — Predictive Multi-Agent System for Airline Disruption Recovery  
**Academic Context:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Team:** Athish Raj (Team Lead & Data/Tools), Dinesh K (Agents & Orchestration), Sanchit Rajesh (Tracing & Evaluation)  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Core Operating Parameters (Approved Phase 0 Blueprint)

- **Primary Hub Airport:** Kempegowda International Airport, Bengaluru (**BLR / VOBL**).
- **Secondary / Spoke Airports:** Delhi (DEL/VIDP), Mumbai (BOM/VABB), Chennai (MAA/VOMM), Hyderabad (HYD/VOHY), Goa (GOI/VOGO), Kolkata (CCU/VECC).
- **Regulatory Standard:** DGCA CAR Section 7, Series J, Part III (2019 baseline in force, with configurable 2024 revised norms toggle).
- **Passenger Care Standard:** DGCA CAR Section 3, Series M, Part IV (cancellations, delays, meals, hotel accommodations).
- **Fleet Scale:** Approximately 15 narrow-body aircraft (Airbus A320 family) over a 24-hour tactical horizon.
- **Human Authority:** Advisory decision-support system. Final plan execution strictly requires Human Duty Manager approval via a web interface or CLI pause.
- **Architectural Proposals Approved:**
  - `PROP-01`: Deterministic schedule mutation via `apply_plan_diff`.
  - `PROP-02`: Normalized composite penalty score $[0, 1]$.
  - `PROP-03`: Normalized SQLite crew duty schema (`crew_members`, `crew_duties`, `crew_duty_flights`).
  - `PROP-04`: Human replan feedback loop upon plan rejection.
  - `PROP-05`: Strict isolation of clean-room `validator_fdtl.py` (runtime agents cannot call it).

---

## 2. Mandatory Engineering Guardrails

1. **Deterministic Calculations Only:**
   - Under no circumstances shall an LLM perform arithmetic, flight duration calculation, duty hour tallying, or slot counting.
   - All numbers must be computed by deterministic Python tools.
2. **Hard Veto Preservation:**
   - Crew Legality and Slot agents possess absolute hard veto authority.
   - A candidate plan with a non-empty `vetoed_by` list can NEVER be recommended or selected by the Mediator, regardless of its cost or delay score.
3. **Bounded Execution:**
   - Negotiation rounds are strictly capped at 3 rounds.
   - Retries, tool calls, and graph loops must have hard exit boundaries.
4. **No Unsubstantiated Claims:**
   - Only claim functionality that is supported by passing tests and actual verification logs.
