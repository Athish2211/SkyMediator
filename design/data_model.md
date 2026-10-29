# SkyMediator — Data Model and Schemas

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Relational Database Schema (SQLite DDL)

To resolve the unnormalized design and relational integrity gaps identified in the architecture review (GAP-05), the SQLite data store is formally specified below. Foreign keys are strictly enabled.

```sql
PRAGMA foreign_keys = ON;

-- 1. Aircraft Table
CREATE TABLE IF NOT EXISTS aircraft (
    tail VARCHAR(16) PRIMARY KEY,
    aircraft_type VARCHAR(16) NOT NULL,
    seats INTEGER NOT NULL CHECK (seats > 0),
    min_turn_min INTEGER NOT NULL DEFAULT 35,
    current_airport VARCHAR(4) NOT NULL,
    maintenance_due_hours REAL NOT NULL DEFAULT 100.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Flights Table
CREATE TABLE IF NOT EXISTS flights (
    flight_id VARCHAR(16) PRIMARY KEY,
    tail VARCHAR(16) NOT NULL,
    origin VARCHAR(4) NOT NULL,
    dest VARCHAR(4) NOT NULL,
    std TIMESTAMP NOT NULL, -- Scheduled Time of Departure
    sta TIMESTAMP NOT NULL, -- Scheduled Time of Arrival
    etd TIMESTAMP,          -- Estimated Time of Departure (updated during disruption)
    eta TIMESTAMP,          -- Estimated Time of Arrival
    seats INTEGER NOT NULL CHECK (seats > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED' 
        CHECK (status IN ('SCHEDULED', 'BOARDING', 'AIRBORNE', 'DELAYED', 'CANCELLED', 'DIVERTED', 'COMPLETED')),
    FOREIGN KEY (tail) REFERENCES aircraft(tail) ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_flights_std ON flights(std);
CREATE INDEX IF NOT EXISTS idx_flights_tail ON flights(tail);
CREATE INDEX IF NOT EXISTS idx_flights_origin_dest ON flights(origin, dest);

-- 3. Weather Observations Table
CREATE TABLE IF NOT EXISTS weather_obs (
    obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    station VARCHAR(4) NOT NULL,
    ts TIMESTAMP NOT NULL,
    visibility_m INTEGER NOT NULL,
    rvr_m INTEGER,
    wind_speed_kts INTEGER NOT NULL,
    wind_dir_deg INTEGER NOT NULL,
    temp_c REAL NOT NULL,
    dewpoint_c REAL NOT NULL,
    cloud_ceiling_ft INTEGER,
    metar_raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weather_station_ts ON weather_obs(station, ts);

-- 4. Crew Members Table
CREATE TABLE IF NOT EXISTS crew_members (
    crew_id VARCHAR(16) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('CAPTAIN', 'FIRST_OFFICER', 'CABIN_LEAD', 'CABIN_CREW')),
    base VARCHAR(4) NOT NULL,
    current_airport VARCHAR(4) NOT NULL,
    cumulative_duty_7d_hours REAL NOT NULL DEFAULT 0.0,
    cumulative_duty_28d_hours REAL NOT NULL DEFAULT 0.0
);

-- 5. Crew Duties Table (Duty Periods)
CREATE TABLE IF NOT EXISTS crew_duties (
    duty_id VARCHAR(32) PRIMARY KEY,
    crew_id VARCHAR(16) NOT NULL,
    duty_start TIMESTAMP NOT NULL,
    duty_end TIMESTAMP,
    rest_period_before_min INTEGER NOT NULL DEFAULT 720,
    max_fdp_minutes INTEGER NOT NULL DEFAULT 780, -- 13 hours standard baseline
    is_split_duty BOOLEAN DEFAULT 0,
    is_augmented BOOLEAN DEFAULT 0,
    FOREIGN KEY (crew_id) REFERENCES crew_members(crew_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_crew_duties_crew_start ON crew_duties(crew_id, duty_start);

-- 6. Crew Duty Flights (Junction Table resolving GAP-05)
CREATE TABLE IF NOT EXISTS crew_duty_flights (
    duty_id VARCHAR(32) NOT NULL,
    flight_id VARCHAR(16) NOT NULL,
    leg_sequence INTEGER NOT NULL,
    is_deadhead BOOLEAN DEFAULT 0,
    PRIMARY KEY (duty_id, flight_id),
    FOREIGN KEY (duty_id) REFERENCES crew_duties(duty_id) ON DELETE CASCADE,
    FOREIGN KEY (flight_id) REFERENCES flights(flight_id) ON UPDATE CASCADE
);

-- 7. Passenger Bookings Table
CREATE TABLE IF NOT EXISTS bookings (
    booking_id VARCHAR(32) PRIMARY KEY,
    pax_count INTEGER NOT NULL CHECK (pax_count > 0),
    fare_class VARCHAR(4) NOT NULL CHECK (fare_class IN ('ECONOMY', 'PREMIUM_ECON', 'BUSINESS')),
    avg_fare_paid REAL NOT NULL CHECK (avg_fare_paid >= 0),
    contact_email VARCHAR(64)
);

-- 8. Itinerary Legs Table
CREATE TABLE IF NOT EXISTS itinerary_legs (
    booking_id VARCHAR(32) NOT NULL,
    leg_no INTEGER NOT NULL,
    flight_id VARCHAR(16) NOT NULL,
    seat_assigned VARCHAR(8),
    PRIMARY KEY (booking_id, leg_no),
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (flight_id) REFERENCES flights(flight_id) ON UPDATE CASCADE
);

-- 9. Passenger Flight Connections Table
CREATE TABLE IF NOT EXISTS connections (
    connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id VARCHAR(32) NOT NULL,
    inbound_flight VARCHAR(16) NOT NULL,
    outbound_flight VARCHAR(16) NOT NULL,
    connection_airport VARCHAR(4) NOT NULL,
    min_connect_min INTEGER NOT NULL DEFAULT 45,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (inbound_flight) REFERENCES flights(flight_id) ON UPDATE CASCADE,
    FOREIGN KEY (outbound_flight) REFERENCES flights(flight_id) ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_connections_flights ON connections(inbound_flight, outbound_flight);

-- 10. Airport Slots and Curfew Table
CREATE TABLE IF NOT EXISTS slots (
    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport VARCHAR(4) NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    curfew_start TIME,
    curfew_end TIME
);
CREATE INDEX IF NOT EXISTS idx_slots_airport_window ON slots(airport, window_start, window_end);

-- 11. Cost Rates Table
CREATE TABLE IF NOT EXISTS cost_rates (
    rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item VARCHAR(64) UNIQUE NOT NULL,
    rate REAL NOT NULL,
    currency VARCHAR(4) NOT NULL DEFAULT 'INR',
    description TEXT
);

-- 12. Pre-seeded Scenarios Table
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    disruption_type VARCHAR(16) NOT NULL,
    airport VARCHAR(4) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    severity VARCHAR(16) NOT NULL,
    difficulty VARCHAR(16) NOT NULL,
    seeded_anomalies TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. Candidate Plan and Plan Diff Schema (Resolving GAP-01)

To allow deterministic verification and eliminate ambiguous text diffs, every plan mutation is modeled as an atomic operation (`PlanDiffOp`):

```python
from typing import Literal, Union, List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class SwapTailOp(BaseModel):
    op: Literal["swap_tail"] = "swap_tail"
    flight_id: str = Field(..., description="Flight ID whose aircraft is reassigned")
    original_tail: str
    new_tail: str
    reason: str

class DelayOp(BaseModel):
    op: Literal["delay"] = "delay"
    flight_id: str
    delay_minutes: int = Field(..., gt=0, description="Minutes to delay departure")
    new_std: datetime
    new_sta: datetime
    reason: str

class CancelOp(BaseModel):
    op: Literal["cancel"] = "cancel"
    flight_id: str
    reason: str
    passenger_rebooking_policy: Literal["AUTOMATIC", "MANUAL", "REFUND_ONLY"] = "AUTOMATIC"

class RepositionCrewOp(BaseModel):
    op: Literal["reposition_crew"] = "reposition_crew"
    crew_id: str
    from_airport: str
    to_airport: str
    flight_id: str = Field(..., description="Operating flight ID or deadhead flight ID")
    is_deadhead: bool = True
    reason: str

PlanDiffOp = Union[SwapTailOp, DelayOp, CancelOp, RepositionCrewOp]

class CandidatePlan(BaseModel):
    plan_id: str
    round_created: int
    proposing_agent: str
    plan_diff: List[PlanDiffOp]
    operational_rationale: str
    scores: Dict[str, float] = Field(default_factory=dict)
    vetoed_by: List[str] = Field(default_factory=list)
    veto_reasons: Dict[str, str] = Field(default_factory=dict)
```

---

## 3. LangGraph Shared Plan State Schema

The shared orchestrator state is defined using Python `TypedDict` and Pydantic validation:

```python
from typing import TypedDict, List, Dict, Any, Optional

class DisruptionState(TypedDict):
    disruption_id: str
    type: str  # "fog" or "aog"
    airport: str
    start: str  # ISO 8601
    end: str    # ISO 8601
    severity: str
    confidence: float

class ConstraintLogEntry(TypedDict):
    round: int
    agent: str
    constraint_type: str  # "FDTL", "SLOT", "MAINTENANCE"
    clause_id: Optional[str]
    reason: str
    target_flight_id: Optional[str]

class MessageRecord(TypedDict):
    message_id: str
    round: int
    from_agent: str
    to_agent: str
    type: str  # "PROPOSE", "VETO", "COUNTER", "ACCEPT", "ABSTAIN", "ESCALATE"
    plan_diff: List[Dict[str, Any]]
    rationale: str
    evidence_refs: List[str]
    timestamp: str

class PlanState(TypedDict):
    run_id: str
    version: int
    round: int
    max_rounds: int
    status: str  # "RUNNING", "INTERRUPTED", "APPROVED", "ESCALATED", "ABORTED"
    disruption: DisruptionState
    base_schedule: List[Dict[str, Any]]
    active_crew: List[Dict[str, Any]]
    affected_pax: Dict[str, Any]
    constraints_log: List[ConstraintLogEntry]
    message_history: List[MessageRecord]
    candidates: List[Dict[str, Any]]  # Serialized CandidatePlan
    surviving_candidates: List[Dict[str, Any]]
    recommended_plan_id: Optional[str]
    duty_manager_decision: Optional[Dict[str, Any]]
    escalation_reason: Optional[str]
```

---

## 4. Observability and Trace Span Schema

Every LLM generation, agent decision, and tool execution writes a structured JSONL record:

```python
class TraceSpan(BaseModel):
    span_id: str
    run_id: str
    round: int
    agent: str
    action_type: Literal["AGENT_INVOCATION", "TOOL_CALL", "VETO_EMITTED", "INTERRUPT_PAUSE", "HUMAN_INPUT"]
    tool_name: Optional[str] = None
    input_payload: Dict[str, Any]
    output_payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tokens_used: int = 0
    latency_ms: float = 0.0
```
