# SkyMediator — Requirements Specification

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Problem Statement and Operational Reality

Airline operations are vulnerable to high-impact external disruptions. At major hub airports, adverse weather phenomena—specifically severe winter fog causing low-visibility conditions (Runway Visual Range falling below Category II/III thresholds)—sharply reduce airport acceptance rates (AAR). 

When runway capacity drops:
1. Aircraft cannot land or take off at scheduled times, triggering ground holding, holding patterns, and diversions.
2. Aircraft rotations cascade into downstream delays, eventually propagating network-wide.
3. Flight crew duty limits (DGCA Flight and Duty Time Limitations — FDTL) expire mid-rotation, resulting in sudden "crew timing out" and uncrewed aircraft at outstations.
4. Passenger itineraries are severed, causing mass missed connections, breached passenger charters, and large accommodation/compensation liabilities under DGCA regulations.
5. Secondary operational disruptions such as Aircraft On Ground (AOG) due to technical snags exacerbate capacity deficits.

In contemporary Operations Control Centers (OCC), human duty managers must resolve these multi-dimensional crises manually under intense time pressure. The objectives are fiercely contradictory:
- Minimizing delay minutes vs. passenger compensation costs.
- Aggressive aircraft swaps vs. violating maintenance routing or crew base rest rules.
- Cancelling low-load flights vs. severing high-value international connections.

**The Decision Supported:**  
SkyMediator is designed to answer a single operational question for the OCC:  
*Which recovery plan (comprising aircraft tail swaps, flight delays, controlled cancellations, and crew repositioning) should the duty manager approve to resolve a fog-induced disruption window while strictly preserving regulatory legality and minimizing total cost?*

---

## 2. Core Operational Philosophy & Safety Boundaries

1. **Advisory Decision Support with Human Confirmation (Human-in-the-Loop):**  
   SkyMediator is strictly an advisory decision-support system. It never executes dispatch, crew assignment, or ATC cancellation commands autonomously. Every final recovery plan requires explicit approval from the Human Duty Manager through a pause-and-interrupt workflow.
2. **Hard Veto vs. Soft Trade-Offs:**  
   Operational goals are divided into non-negotiable legal/operational boundaries and soft economic objectives:
   - **Hard Constraints (Zero Tolerance):** Crew flight duty limits (DGCA CAR Section 7, Series J, Part III) and airport curfew/slot allocations cannot be traded off against cost or delay. Hard veto agents have absolute authority to discard candidate plans.
   - **Soft Constraints (Optimization Objectives):** Passenger delays, missed connections, passenger care costs (meals, hotels, compensation under DGCA CAR Section 3, Series M, Part IV), and aircraft turn buffers are evaluated and ranked via a weighted multi-objective scoring function.
3. **Deterministic Arithmetic Guarantee:**  
   Large Language Models (LLMs) are strictly prohibited from performing mental arithmetic, flight time accumulation, cost summation, or slot capacity verification. All mathematical calculations, schedule mutations, and constraint checks are performed by deterministic, unit-tested Python functions. LLMs function exclusively for semantic reasoning, RAG clause interpretation, counter-proposal synthesis, and natural language justification.
4. **Agentic RAG with Self-Grading and Abstention:**  
   When interpreting regulatory clauses, the Crew Legality agent uses an agentic retrieval-augmented generation (RAG) loop: retrieve relevant clauses, grade clause applicability, rewrite queries if retrieval confidence is low, and abstain/escalate if ambiguity persists. The system never vetoes or approves based on regulatory hallucinations.
5. **Bounded Negotiation:**  
   The multi-agent deliberation loop is strictly bounded by a 3-round cap, a hard token budget, and an improvement convergence threshold to guarantee real-time OCC responsiveness.

---

## 3. Scope and Operating Boundaries

| Dimension | Specification | Notes / Rationale |
| :--- | :--- | :--- |
| **Hub Airport** | Single Hub Airport (Primary: Indira Gandhi International Airport - DEL / VIDP; Fallback: Chicago O'Hare - ORD) | High winter fog frequency (December–February) causing severe CAT III operations. |
| **Disruption Type** | Winter Fog (Low Visibility Procedures / Capacity reduction) + AOG secondary risk | Predictable onset, high operational impact, standard benchmark. |
| **Planning Window** | 24 Hours (Rolling Horizon) | Covers the tactical day-of-operation recovery cycle. |
| **Fleet Scale** | Approximately 15 aircraft (Narrow-body, e.g., A320/B737 family) | Realistically sized sub-fleet representing a dedicated hub rotation pool. |
| **Flight Volume** | 40–80 flights over the 24-hour window | Sufficient density to test complex turnarounds, swaps, and crew handoffs. |
| **Data Hybridity** | Hybrid Data Design | Real flight schedules and weather observations anchored to synthetic, seeded crew pairings and passenger itineraries. |
| **Language Model** | Local or Free-Tier LLM | Ollama (Llama-3-8B / Qwen-2.5) or Free-Tier Cloud (Gemini 1.5 Flash / Groq). |

---

## 4. Functional Requirements

### FR-1: Environmental Ingestion and Disruption Prediction
- **FR-1.1:** The system shall ingest METAR/SPECI weather observations (visibility, Runway Visual Range [RVR], dew point depression, wind speed, cloud ceiling) for the hub airport.
- **FR-1.2:** The `Sentinel` agent shall run a deterministic feature-extraction pipeline and a trained machine learning model (`scikit-learn`) to output disruption probability, predicted start/end time, lead time, and confidence level.
- **FR-1.3:** The system shall support both *predictive* trigger (Sentinel flags fog risk > threshold prior to onset) and *reactive* trigger (external disruption event injected directly into the orchestrator).

### FR-2: Operational State Representation and Isolation
- **FR-2.1:** Operational data shall be persisted in a normalized SQLite database containing flights, aircraft, crew pairings, bookings, itinerary legs, connections, slot capacities, and cost rates.
- **FR-2.2:** The shared plan state within LangGraph shall be versioned, immutable across rounds, and isolated from direct database mutation during deliberation.
- **FR-2.3:** Changes to candidate plans shall be expressed strictly as differential operations (`PlanDiffOp`: tail swaps, departure delays, cancellations, crew deadheading/repositioning).

### FR-3: Candidate Plan Generation
- **FR-3.1:** The `Rotation` agent shall analyze the disruption window, identify grounded or delayed aircraft, and propose one or more candidate recovery plans expressed as structured `PlanDiff` objects.
- **FR-3.2:** Proposable operations shall be restricted to:
  1. `swap_tail`: Swapping aircraft between flight legs with identical equipment compatibility.
  2. `delay`: Delaying departure within acceptable maintenance and passenger windows.
  3. `cancel`: Selectively cancelling flight legs to prevent severe downstream network collapse.
  4. `reposition_crew`: Assigning deadhead crew to recover uncrewed legs.
- **FR-3.3:** The `Rotation` agent shall call deterministic schedule query and aircraft turnaround validation tools to ensure tail continuity and minimum turnaround times (`min_turn_min`).

### FR-4: Hard Legality Checks and Veto Authority
- **FR-4.1:** **Crew Legality Agent:**
  - Must evaluate proposed candidate plans against DGCA CAR Section 7, Series J, Part III (Flight and Duty Time Limitations and Rest Requirements).
  - Must use the deterministic tool `calc_duty_time` to calculate cumulative flight duty periods (FDP), night operations within the Window of Circadian Low (WOCL), and mandatory rest periods.
  - Must use Agentic RAG to retrieve exact CAR clauses, evaluate clause coverage, and attach clause references (`clause_id`) to every veto.
  - Has absolute veto power: If FDTL is breached, the candidate plan is marked `vetoed_by: ["crew"]` with cited rationale.
- **FR-4.2:** **Slot Agent:**
  - Must evaluate candidate plan arrivals and departures against airport slot capacity windows (e.g., max 15 movements per 30-minute block during fog) and night curfews.
  - Must call the deterministic tool `check_slot` to detect slot window overflows.
  - Has absolute veto power: If an airport curfew or slot limit is breached, the plan is marked `vetoed_by: ["slot"]`.

### FR-5: Impact Assessment and Soft Scoring
- **FR-5.1:** **Passenger Agent:**
  - Must evaluate surviving (unvetoed) candidate plans using deterministic tools: `get_affected_bookings`, `calc_missed_connections`, and `get_rebooking_options`.
  - Must output the exact count of disrupted passengers, broken connections, and available seat rebooking capacities on alternative flights.
- **FR-5.2:** **Cost Agent:**
  - Must price candidate plans deterministically using `estimate_cost` across standardized cost categories:
    1. Flight delay cost (crew overtime, fuel burn, ground handling).
    2. Flight cancellation cost (lost ticket revenue, rebooking costs).
    3. Passenger care and compensation liabilities under DGCA CAR Section 3, Series M, Part IV (meals/refreshments for delays > 2 hrs, hotel accommodation for delays > 24 hrs or overnight, statutory cancellation compensation).
- **FR-5.3:** **Mediator Agent:**
  - Must hard-filter all vetoed candidate plans.
  - Must calculate a composite scalar score for all surviving candidates using a deterministic, normalized scoring function:
    $$\text{Score} = w_1 \cdot \text{NormalizedDelay} + w_2 \cdot \text{NormalizedMissedConnections} + w_3 \cdot \text{NormalizedCost} + w_4 \cdot \text{CrewBufferPenalty}$$
  - Weights ($w_1, w_2, w_3, w_4$) must be configurable.

### FR-6: Negotiation, Deliberation Loop, and Reflection
- **FR-6.1:** When candidate plans are vetoed, the Mediator or proposing agents shall formulate counter-proposals in subsequent rounds (incorporating veto feedback).
- **FR-6.2:** The negotiation loop shall terminate upon any of the following conditions:
  1. Convergence: A candidate plan achieves consensus with zero hard vetoes and score improvement between rounds falls below $\epsilon$.
  2. Round Exhaustion: Exactly 3 deliberation rounds are completed.
  3. Budget Exhaustion: Allocated token budget for the deliberation session is reached.
- **FR-6.3:** The Mediator shall perform a final reflection pass over the top-ranked plan to verify consistency before presenting it to the duty manager.

### FR-7: Human-in-the-Loop Approval and Escalation
- **FR-7.1:** The orchestrator must execute a LangGraph `interrupt()` pause when deliberation concludes.
- **FR-7.2:** The system shall escalate to the human duty manager under the following mandatory escalation conditions:
  - All proposed plans were vetoed by hard agents.
  - The top two surviving candidate plans have scores within a configurable indifference margin ($\delta \le 5\%$).
  - Any agent returned an `ABSTAIN` due to low retrieval confidence or missing data.
  - RAG retrieval evidence remained weak after query rewriting.
- **FR-7.3:** The Duty Manager interface must display:
  - Candidate comparison matrix (Delays, Missed Connections, Costs, Veto logs).
  - Cited regulatory clauses and tool evidence for all recommendations.
  - Options to: `APPROVE`, `REJECT`, `SELECT_ALTERNATIVE`, or `REQUEST_REPLAN`.

---

## 5. Non-Functional Requirements

### NFR-1: Computational and Arithmetic Determinism
- Under no circumstances shall an LLM compute flight minutes, cost figures, or slot capacity sums.
- Every numeric figure displayed in state, messages, or reports must originate from a Python tool return value with a traceable tool call ID.

### NFR-2: Bounded Orchestration and Resource Consumption
- Total deliberation rounds per disruption scenario shall not exceed 3.
- Tool execution timeout: Deterministic tools must execute in $< 500\text{ ms}$.
- Deliberation latency: Total end-to-end multi-agent negotiation must complete in $< 60\text{ seconds}$ on standard hardware.

### NFR-3: Repeatability, Seed Isolation, and Synthetic Data Integrity
- Synthetic passenger and crew generation must use explicit pseudo-random seeds (`seed=42`).
- Rebuilding the database from identical raw inputs and seeds must yield byte-for-byte identical SQLite databases.
- Scenarios must be serializable and reproducible across test runs.

### NFR-4: Observability, Tracing, and Auditability
- Every agent invocation, LLM prompt/response, tool call (input and output), and state transition must be logged as a structured `TraceSpan` in JSONL format.
- Traces must record `run_id`, `round`, `agent`, `tool`, `input`, `output`, `timestamp`, and `token_count`.

### NFR-5: Regulatory and Legal Fidelity
- RAG retrieval must index the official text of DGCA Civil Aviation Requirements (CAR).
- Veto citations must reference the exact section, series, part, and paragraph (e.g., `CAR Sec 7, Series J, Part III, Para 6.2`).
- Independent validation in `eval/validator_fdtl.py` must maintain a distinct, clean-room implementation of FDTL rules to verify candidate plans without circular dependencies.

---

## 6. Assumptions and Dependencies

1. **Weather Ingestion:** METAR reports are retrievable from Iowa Environmental Mesonet (IEM) or NOAA NCEI for the chosen hub airport. If network access is restricted during local runs, pre-downloaded historical METAR archives will be utilized.
2. **Flight Schedule Availability:** Real commercial schedules are sourced from public filings (DGCA or BTS fallback). Synthetic generators anchor aircraft tails and passenger flows to these real flights.
3. **Regulatory Grounding:** DGCA CAR Section 7, Series J, Part III (2019 baseline) serves as the primary FDTL standard, with configuration flags to evaluate the 2024 revised norms.
4. **Execution Environment:** Python 3.10+ on Windows/Linux with LangGraph $\ge 0.2$, SQLite3, and scikit-learn $\ge 1.3$.
