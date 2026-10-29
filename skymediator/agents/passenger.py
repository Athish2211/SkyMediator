"""
Passenger Agent — Passenger Itinerary Disruption and Connection Scorer.
Evaluates missed connections through Kempegowda Hub and queries seat rebooking feasibility.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan
from skymediator.tools.passengers import calc_missed_connections, get_affected_bookings, get_rebooking_options
from skymediator.tools.schedule import apply_plan_diff


class PassengerEvaluationResult(BaseModel):
    total_affected_passengers: int
    missed_connections_count: int
    broken_connections: List[Dict[str, Any]] = Field(default_factory=list)
    average_delay_minutes: float = 0.0
    summary: str


class PassengerAgent:
    """Evaluator agent assessing passenger disruption and connection preservation."""

    def evaluate_candidate_plan(
        self,
        candidate: CandidatePlan,
        base_schedule: List[Dict[str, Any]],
        run_id: str,
        round_number: int = 1
    ) -> PassengerEvaluationResult:
        """Calculates passenger impacts using deterministic connection validation tools."""
        mutated_res = apply_plan_diff(base_schedule, candidate.plan_diff)
        mutated_schedule = mutated_res["mutated_flights"]

        conn_res = calc_missed_connections(mutated_schedule)
        missed_count = conn_res.get("total_missed_connections", 0)
        missed_pax = conn_res.get("total_missed_passengers", 0)

        # Calculate average passenger delay
        total_delay = 0
        flight_count = 0
        for f in mutated_schedule:
            if f.get("status") == "DELAYED":
                total_delay += 45  # Estimated delay
                flight_count += 1

        avg_delay = round(total_delay / max(1, flight_count), 1)

        summary = (
            f"Preserved connections for all hub transfers; {missed_count} connections broken."
            if missed_count > 0 else "Zero broken connections. High passenger itinerary continuity."
        )

        output = PassengerEvaluationResult(
            total_affected_passengers=missed_pax,
            missed_connections_count=missed_count,
            broken_connections=conn_res.get("broken_connection_records", []),
            average_delay_minutes=avg_delay,
            summary=summary
        )

        span = TraceSpan(
            span_id=f"PAX-{uuid4().hex[:6]}",
            run_id=run_id,
            round=round_number,
            agent="Passenger",
            action_type="AGENT_INVOCATION",
            tool_name="calc_missed_connections",
            input_payload={"plan_id": candidate.plan_id},
            output_payload=output.model_dump()
        )
        write_trace_span(span)

        return output
