"""
Cost Agent — Financial Impact and Statutory Compensation Estimator.
Prices candidate plans deterministically across operational delay, cancellations,
and DGCA CAR Section 3 statutory passenger liabilities.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan
from skymediator.tools.cost import estimate_cost
from skymediator.tools.schedule import apply_plan_diff


class CostEvaluationResult(BaseModel):
    delay_cost: float
    cancellation_cost: float
    meal_care_cost: float
    hotel_care_cost: float
    statutory_compensation_cost: float
    total_cost: float
    currency: str = "INR"
    cost_saving_hints: List[str] = Field(default_factory=list)


class CostAgent:
    """Evaluator agent pricing plans and advising on cost-effective recovery trade-offs."""

    def evaluate_candidate_plan(
        self,
        candidate: CandidatePlan,
        base_schedule: List[Dict[str, Any]],
        missed_connections: int,
        run_id: str,
        round_number: int = 1
    ) -> CostEvaluationResult:
        """Calculates exact financial liabilities using deterministic cost estimator."""
        mutated_res = apply_plan_diff(base_schedule, candidate.plan_diff)
        mutated_schedule = mutated_res["mutated_flights"]

        cost_res = estimate_cost(
            mutated_schedule=mutated_schedule,
            missed_connections_count=missed_connections
        )

        hints = []
        if cost_res["cancellation_cost"] > cost_res["delay_cost"] * 3:
            hints.append("Cancellation penalty exceeds delay cost significantly. Recommend delay or tail swap if slot permits.")
        if cost_res["hotel_care_cost"] > 50000:
            hints.append("High hotel accommodation liability due to overnight stranded passengers. Prioritize rebooking on evening departures.")

        output = CostEvaluationResult(
            delay_cost=cost_res["delay_cost"],
            cancellation_cost=cost_res["cancellation_cost"],
            meal_care_cost=cost_res["meal_care_cost"],
            hotel_care_cost=cost_res["hotel_care_cost"],
            statutory_compensation_cost=cost_res["statutory_compensation_cost"],
            total_cost=cost_res["total_cost"],
            currency=cost_res["currency"],
            cost_saving_hints=hints
        )

        span = TraceSpan(
            span_id=f"COST-{uuid4().hex[:6]}",
            run_id=run_id,
            round=round_number,
            agent="Cost",
            action_type="AGENT_INVOCATION",
            tool_name="estimate_cost",
            input_payload={"plan_id": candidate.plan_id},
            output_payload=output.model_dump()
        )
        write_trace_span(span)

        return output
