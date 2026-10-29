# SkyMediator — Agent Contracts and Deliberation Specifications

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Overview and Agent Taxonomy

In SkyMediator, seven specialized autonomous agents and one human supervisor collaborate to resolve airline disruptions. Each agent operates under a strict contract defining its decision authority, permitted deterministic tools, input/output schemas, and failure modes.

### Agent Authority Matrix

| Agent | Authority Type | Decision Power | Tool Execution Mode | Primary Concern |
| :--- | :--- | :--- | :--- | :--- |
| **Sentinel** | Predictive / Advisory | Suggests pre-positioning / monitoring | Deterministic features + ML classifier | Disruption probability and timing |
| **Rotation** | Operational Proposer | Proposes aircraft tail swaps, delays, cancellations | Deterministic schedule query & turn checks | Aircraft continuity & fleet integrity |
| **Crew Legality** | Hard Veto | Can veto candidate plans; absolute stop authority | Deterministic FDTL calculator + Agentic RAG | DGCA CAR FDTL compliance |
| **Slot** | Hard Veto | Can veto candidate plans; absolute stop authority | Deterministic slot & curfew checker | Airport movement capacity & curfews |
| **Passenger** | Evaluator / Scorer | Computes passenger impact metrics | Deterministic booking & connection tools | Missed connections & rebooking feasibility |
| **Cost** | Evaluator / Advisor | Prices plans & suggests financial optimizations | Deterministic cost estimator | Operational costs & statutory liabilities |
| **Mediator** | Orchestrator / Decider | Directs rounds, ranks plans, triggers human interrupt | Deterministic composite scoring & reflection | Global Pareto efficiency & consensus |
| **Duty Manager** | Human-in-the-Loop | Final approval or rejection authority | Interactive CLI / Web UI review | Operational viability & strategic sign-off |

---

## 2. Sentinel Agent Contract

### 2.1 Role and Responsibility
Monitors weather reports (METAR/SPECI) and technical fault logs to predict disruptions (severe fog or AOG) before they impact operations. Emits advisory early-warning alerts.

### 2.2 Decision Power
**Advisory only.** Cannot modify flight schedules or veto recovery plans.

### 2.3 Permitted Tools
- `get_forecast(airport: str, window_hours: int) -> List[Dict]`
- `fog_risk_model(features: Dict) -> Dict`
- `aog_risk(tail: str) -> Dict`

### 2.4 Input Schema
```python
class SentinelInput(BaseModel):
    airport: str
    target_window_start: datetime
    target_window_end: datetime
    historical_metar_window: int = 12  # hours of prior observations
```

### 2.5 Output Schema
```python
class SentinelOutput(BaseModel):
    disruption_detected: bool
    event_type: Literal["fog", "aog", "none"]
    probability: float = Field(ge=0.0, le=1.0)
    expected_start: Optional[datetime]
    expected_end: Optional[datetime]
    expected_lead_time_hours: float
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: Literal["monitor", "pre_position", "act_early", "standby"]
    rationale: str
```

### 2.6 Guardrails and Abstention
- If weather feature completeness is $< 70\%$ (e.g., missing dew point and visibility simultaneously), the agent must output `confidence: 0.0` and `recommended_action: "monitor"`.
- Under no circumstances does the Sentinel trigger schedule cancellations directly.

---

## 3. Rotation Agent Contract

### 3.1 Role and Responsibility
The operational architect of candidate recovery plans. Identifies delayed or trapped aircraft during the disruption window and formulates discrete recovery actions: tail swaps, delay propagation, flight cancellations, and crew repositioning.

### 3.2 Decision Power
**Proposer.** Generates candidate plans (`PlanDiff`). Does not score financial cost or judge legal compliance.

### 3.3 Permitted Tools
- `query_schedule(flight_ids: Optional[List[str]], window_start: Optional[datetime], window_end: Optional[datetime]) -> List[FlightRow]`
- `swap_tail(flight_id: str, new_tail: str, current_state: Dict) -> ValidationResult`
- `check_range_maint(tail: str, flight_id: str) -> ValidationResult`

### 3.4 Input Schema
```python
class RotationInput(BaseModel):
    round_number: int
    disrupted_flights: List[str]
    available_tails: List[str]
    active_constraints_log: List[ConstraintLogEntry]
    previous_vetoes: List[VetoRecord]
```

### 3.5 Output Schema
```python
class RotationOutput(BaseModel):
    candidate_id: str
    plan_diff: List[PlanDiffOp]  # SwapTail, Delay, Cancel, RepositionCrew
    operational_rationale: str
    affected_flight_count: int
```

### 3.6 Deliberation Protocol
1. In Round 1, propose a minimal-delay swap plan.
2. In Round 2+, inspect `previous_vetoes`. If Crew Legality vetoed a leg due to FDTL exceedance on Tail Swap X, formulate an alternative using delay or a different tail.
3. If no feasible tail swap exists without exceeding turnaround limits (`min_turn_min`), propose a strategic cancellation on the lowest-load leg.

---

## 4. Crew Legality Agent Contract (Agentic RAG)

### 4.1 Role and Responsibility
Enforces compliance with DGCA CAR Section 7, Series J, Part III (Flight and Duty Time Limitations and Rest Requirements). Evaluates crew duty periods, cumulative block hours, night duty within the Window of Circadian Low (WOCL), and rest requirements.

### 4.2 Decision Power
**Hard Veto.** If a candidate plan breaches statutory FDTL rules, the agent marks the plan `VETO` and issues a binding rejection citing the exact regulatory clause.

### 4.3 Permitted Tools
- `calc_duty_time(crew_id: str, plan_diff: List[PlanDiffOp], base_state: Dict) -> DutyCalculationResult`
- `retrieve_fdtl(query: str, k: int = 3) -> List[RetrievedClauseChunk]`

### 4.4 Input Schema
```python
class CrewLegalityInput(BaseModel):
    candidate_id: str
    plan_diff: List[PlanDiffOp]
    crew_rosters: List[CrewMember]
```

### 4.5 Output Schema
```python
class CrewLegalityOutput(BaseModel):
    candidate_id: str
    decision: Literal["PASS", "VETO", "ABSTAIN"]
    violations: List[FDTLViolation]
    cited_clauses: List[str]  # e.g., ["CAR Sec 7, Series J, Part III, Para 6.2"]
    retrieval_confidence: float
    reasoning: str
```

### 4.6 Agentic RAG Protocol
1. Call `calc_duty_time` for all crew members assigned to altered flights.
2. If duty violations are detected (e.g., FDP = 13.5 hours, limit = 12.5 hours):
   a. Draft query: `"maximum flight duty period for 2 landings duty start 0600"`.
   b. Call `retrieve_fdtl`.
   c. **Self-Grade Relevance:** Evaluate if retrieved clause explicitly covers the specific case (split duty, night operation, or multi-sector).
   d. **Self-Query Rewrite:** If relevance score $< 0.7$, rewrite the query with regulatory keywords and retrieve once more.
   e. If retrieved clause confirms violation, output `VETO` with cited clause.
   f. If retrieval is contradictory or inconclusive, output `ABSTAIN` and escalate. **Never veto on a hallucination.**

---

## 5. Slot Agent Contract

### 5.1 Role and Responsibility
Validates candidate plans against airport infrastructure constraints: arrival/departure slot capacities per 30-minute window during fog restrictions, and night curfew closures at arrival destinations.

### 5.2 Decision Power
**Hard Veto.** Absolute authority to veto any plan that schedules movements exceeding degraded airport slot capacities or breaches night curfews.

### 5.3 Permitted Tools
- `check_slot(plan_diff: List[PlanDiffOp], base_state: Dict) -> SlotValidationResult`

### 5.4 Input Schema
```python
class SlotInput(BaseModel):
    candidate_id: str
    plan_diff: List[PlanDiffOp]
    airport_code: str
```

### 5.5 Output Schema
```python
class SlotOutput(BaseModel):
    candidate_id: str
    decision: Literal["PASS", "VETO"]
    violated_windows: List[SlotViolationWindow]
    curfew_breaches: List[CurfewBreach]
    reasoning: str
```

---

## 6. Passenger Agent Contract

### 6.1 Role and Responsibility
Quantifies passenger disruption for unvetoed candidate plans. Analyzes delayed flights to detect broken connections, counts stranded passengers, and evaluates seat rebooking feasibility on alternative flights.

### 6.2 Decision Power
**Evaluator / Scorer.** Emits passenger impact metrics. Cannot veto plans directly.

### 6.3 Permitted Tools
- `get_affected_bookings(flight_ids: List[str]) -> List[BookingRecord]`
- `calc_missed_connections(plan_diff: List[PlanDiffOp], base_state: Dict) -> MissedConnectionsResult`
- `get_rebooking_options(booking_id: str, plan_diff: List[PlanDiffOp]) -> RebookingResult`

### 6.4 Input Schema
```python
class PassengerInput(BaseModel):
    candidate_id: str
    plan_diff: List[PlanDiffOp]
```

### 6.5 Output Schema
```python
class PassengerOutput(BaseModel):
    candidate_id: str
    total_affected_passengers: int
    missed_connections_count: int
    unrebookable_passengers_count: int
    average_passenger_delay_minutes: float
    itinerary_impact_summary: str
```

---

## 7. Cost Agent Contract

### 7.1 Role and Responsibility
Calculates deterministic operational and regulatory financial costs of candidate plans and advises Rotation on cost-optimal trade-offs.

### 7.2 Decision Power
**Evaluator / Advisor.** Calculates exact costs. Can emit counter-proposals or cost-reduction recommendations to the Mediator.

### 7.3 Permitted Tools
- `estimate_cost(plan_diff: List[PlanDiffOp], base_state: Dict) -> CostBreakdownResult`

### 7.4 Input Schema
```python
class CostInput(BaseModel):
    candidate_id: str
    plan_diff: List[PlanDiffOp]
```

### 7.5 Output Schema
```python
class CostOutput(BaseModel):
    candidate_id: str
    delay_cost: float
    cancellation_cost: float
    passenger_care_cost: float  # Meals (delay > 2h), Hotels (delay > 24h/overnight)
    statutory_compensation: float  # Under DGCA CAR Sec 3, Series M, Part IV
    total_cost: float
    currency: Literal["INR", "USD"]
    cost_saving_hints: List[str]
```

---

## 8. Mediator Agent Contract

### 8.1 Role and Responsibility
The coordinator of the multi-agent deliberation loop. Enforces hard veto filtering, executes deterministic multi-objective scoring, reflects on systemic trade-offs, drives round transitions, and escalates to the Duty Manager.

### 8.2 Decision Power
**Orchestrator and Ranker.** Filters vetoed plans, selects the top-ranked plan, and controls workflow transitions.

### 8.3 Permitted Tools
- `score_plan(metrics: CandidateMetrics, weights: Dict[str, float]) -> ScoreResult`
- `round_counter(current_round: int) -> int`

### 8.4 Input Schema
```python
class MediatorInput(BaseModel):
    round_number: int
    candidate_plans: List[CandidatePlan]
    agent_reports: Dict[str, Any]  # Crew, Slot, Pax, Cost outputs
    convergence_history: List[RoundScoreRecord]
```

### 8.5 Output Schema
```python
class MediatorOutput(BaseModel):
    status: Literal["CONTINUE_DELIBERATION", "READY_FOR_APPROVAL", "ESCALATE"]
    top_candidate_id: Optional[str]
    ranked_candidates: List[RankedCandidate]
    reflection_notes: str
    escalation_reason: Optional[str]
```

### 8.6 Deliberation and Reflection Protocol
1. **Hard Filtering:** Immediately discard any candidate where `vetoed_by` is non-empty.
2. **Deterministic Scoring:** For surviving candidates, call `score_plan` using normalized weights ($w_{\text{delay}}=0.30, w_{\text{pax}}=0.30, w_{\text{cost}}=0.30, w_{\text{crew}}=0.10$).
3. **Reflection Pass:** Verify whether the top plan creates severe secondary trade-offs (e.g., zero delay but complete stranding of 100 passengers).
4. **Escalation Triggers:**
   - All proposed plans were vetoed.
   - The top two candidates have score differences $\le 0.05$ (ambiguity / margin of indifference).
   - Any agent emitted `decision: "ABSTAIN"`.
   - Max round (3) reached without convergence.

---

## 9. Human Duty Manager Contract (Human-in-the-Loop)

### 9.1 Role and Responsibility
The ultimate decision authority in the OCC. Receives the recommended plan via a LangGraph `interrupt()`, inspects trade-offs, and authorizes execution.

### 9.2 Interaction Interface
```python
class DutyManagerDecision(BaseModel):
    action: Literal["APPROVE", "REJECT", "SELECT_ALTERNATIVE", "MODIFY_AND_REPLAN"]
    selected_plan_id: Optional[str]
    injected_constraints: Optional[List[str]]  # e.g., ["Lock flight 204 from cancellation"]
    manager_signature: str
    timestamp: datetime
```
