"""
Data schemas and type definitions for SkyMediator.
Includes operational entities, plan mutation operations, candidate plans, and LangGraph state.
"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, computed_field
from typing_extensions import TypedDict


# --- Operational Entities ---

class Aircraft(BaseModel):
    tail: str
    aircraft_type: str = "A320"
    seats: int = 180
    min_turn_min: int = 35
    current_airport: str = "VOBL"
    maintenance_due_hours: float = 100.0


class Flight(BaseModel):
    flight_id: str
    tail: str
    origin: str
    dest: str
    std: datetime  # Scheduled Time of Departure
    sta: datetime  # Scheduled Time of Arrival
    etd: Optional[datetime] = None  # Estimated Time of Departure
    eta: Optional[datetime] = None  # Estimated Time of Arrival
    seats: int = 180
    status: Literal[
        "SCHEDULED", "BOARDING", "AIRBORNE", "DELAYED", "CANCELLED", "DIVERTED", "COMPLETED"
    ] = "SCHEDULED"


class CrewMember(BaseModel):
    crew_id: str
    name: str
    role: Literal["CAPTAIN", "FIRST_OFFICER", "CABIN_LEAD", "CABIN_CREW"]
    base: str = "VOBL"
    current_airport: str = "VOBL"
    cumulative_duty_7d_hours: float = 0.0


class CrewDuty(BaseModel):
    duty_id: str
    crew_id: str
    duty_start: datetime
    duty_end: Optional[datetime] = None
    rest_period_before_min: int = 720  # 12 hours minimum rest
    max_fdp_minutes: int = 750         # 12.5 hours standard base FDP for 2 landings


class CrewDutyFlight(BaseModel):
    duty_id: str
    flight_id: str
    leg_sequence: int
    is_deadhead: bool = False


class Booking(BaseModel):
    booking_id: str
    pax_count: int = 1
    fare_class: Literal["ECONOMY", "PREMIUM_ECON", "BUSINESS"] = "ECONOMY"
    avg_fare_paid: float = 4500.0


class Connection(BaseModel):
    connection_id: Optional[int] = None
    booking_id: str
    inbound_flight: str
    outbound_flight: str
    connection_airport: str = "VOBL"
    min_connect_min: int = 45


class SlotWindow(BaseModel):
    slot_id: Optional[int] = None
    airport: str = "VOBL"
    window_start: datetime
    window_end: datetime
    capacity: int = 20  # Max aircraft movements in 30-min window
    curfew_start: Optional[str] = None
    curfew_end: Optional[str] = None


class DisruptionEvent(BaseModel):
    disruption_id: str
    type: Literal["fog", "aog"]
    airport: str = "VOBL"
    start_time: datetime
    end_time: datetime
    severity: Literal["LOW", "MODERATE", "SEVERE"] = "SEVERE"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# --- Plan Mutation Operations (Resolving GAP-01 & PROP-01) ---

class SwapTailOp(BaseModel):
    op: Literal["swap_tail"] = "swap_tail"
    flight_id: str
    original_tail: str
    new_tail: str
    reason: str


class DelayOp(BaseModel):
    op: Literal["delay"] = "delay"
    flight_id: str
    delay_minutes: int = Field(..., gt=0)
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
    flight_id: str
    is_deadhead: bool = True
    reason: str


PlanDiffOp = Annotated[
    Union[SwapTailOp, DelayOp, CancelOp, RepositionCrewOp],
    Field(discriminator="op")
]


class CandidatePlan(BaseModel):
    plan_id: str
    round_created: int
    proposing_agent: str
    plan_diff: List[PlanDiffOp]
    operational_rationale: str
    scores: Dict[str, float] = Field(default_factory=dict)
    vetoed_by: List[str] = Field(default_factory=list)
    veto_reasons: Dict[str, str] = Field(default_factory=dict)
    compliance_notes: Dict[str, str] = Field(default_factory=dict)
    agent_perspectives: Dict[str, str] = Field(default_factory=dict)
    occ_briefing: Optional[str] = None

    @computed_field
    @property
    def is_feasible(self) -> bool:
        return len(self.vetoed_by) == 0


class ConstraintLogEntry(BaseModel):
    round: int
    agent: str
    constraint_type: Literal["FDTL", "SLOT", "MAINTENANCE", "TURNAROUND"]
    clause_id: Optional[str] = None
    reason: str
    target_flight_id: Optional[str] = None


# --- LangGraph Shared State ---

class PlanState(TypedDict, total=False):
    run_id: str
    version: int
    round: int
    max_rounds: int
    status: str  # "INITIALIZED", "DELIBERATING", "AWAITING_APPROVAL", "APPROVED", "ESCALATED", "REJECTED"
    duty_manager_message: Optional[str]
    parsed_disruption: Optional[Dict[str, Any]]
    disruption: Dict[str, Any]
    base_schedule: List[Dict[str, Any]]
    active_crew: List[Dict[str, Any]]
    slot_windows: List[Dict[str, Any]]
    constraints_log: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    surviving_candidates: List[Dict[str, Any]]
    selected_plan: Optional[Dict[str, Any]]
    escalation_reason: Optional[str]
    duty_manager_decision: Optional[Dict[str, Any]]
    sentinel_forecast: Optional[Dict[str, Any]]
    passenger_reports: Optional[Dict[str, Any]]
    cost_reports: Optional[Dict[str, Any]]
    crew_decision: Optional[str]
    slot_decision: Optional[str]
    reflection_notes: Optional[str]
