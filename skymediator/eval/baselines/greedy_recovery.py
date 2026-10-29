"""
Greedy Disruption Recovery Baseline (Task T-7.1).
Rule-based recovery heuristic that resolves disruptions sequentially without multi-agent
negotiation, regulatory RAG, or holistic cost optimization.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from skymediator.models import CandidatePlan, DelayOp, SwapTailOp, CancelOp
from skymediator.tools.scoring import score_plan
from skymediator.tools.schedule import apply_plan_diff


def run_greedy_recovery(
    disruption: Dict[str, Any],
    base_schedule: List[Dict[str, Any]],
    active_crew: Optional[List[Dict[str, Any]]] = None,
    max_delay_threshold_min: int = 240
) -> Dict[str, Any]:
    """
    Executes a greedy recovery strategy:
    1. If AOG: aggressively swaps to first available tail; if none, cancels.
    2. If Fog / Weather: applies full operational delay up to max_delay_threshold_min.
       If delay exceeds threshold, greedily cancels the flight.
    3. Does NOT consult Crew Legality or Slot availability, frequently leading to statutory violations.
    """
    affected_id = disruption.get("affected_flight_id", "6E-101")
    disruption_type = disruption.get("type", "fog")
    delay_min = disruption.get("delay_minutes", 180)
    target_flight = next((f for f in base_schedule if f["flight_id"] == affected_id), None)

    plan_diff: List[Dict[str, Any]] = []
    action_type = "delay"

    if not target_flight:
        return {
            "status": "FAILED",
            "reason": f"Flight {affected_id} not found in schedule",
            "plan_diff": [],
            "scores": {"composite_score": 1.0}
        }

    std_dt = datetime.fromisoformat(target_flight["std"])
    sta_dt = datetime.fromisoformat(target_flight["sta"])

    if disruption_type == "aog":
        candidate_tail = disruption.get("candidate_tail", "VT-BLR15")
        plan_diff = [
            SwapTailOp(
                flight_id=affected_id,
                original_tail=target_flight["tail"],
                new_tail=candidate_tail,
                reason="Greedy rule: Immediate aircraft swap to standby tail"
            ).model_dump()
        ]
        action_type = "swap_tail"

    elif delay_min > max_delay_threshold_min or disruption.get("initial_action") == "cancel":
        plan_diff = [
            CancelOp(
                flight_id=affected_id,
                reason=f"Greedy rule: Delay {delay_min}m exceeds threshold {max_delay_threshold_min}m; cancel flight"
            ).model_dump()
        ]
        action_type = "cancel"

    else:
        plan_diff = [
            DelayOp(
                flight_id=affected_id,
                delay_minutes=delay_min,
                new_std=std_dt + timedelta(minutes=delay_min),
                new_sta=sta_dt + timedelta(minutes=delay_min),
                reason=f"Greedy rule: Delay flight by full disruption duration ({delay_min}m)"
            ).model_dump()
        ]
        action_type = "delay"

    # Deterministic scoring
    total_delay = delay_min if action_type == "delay" else 0.0
    cancellation_cost = 250000.0 if action_type == "cancel" else 0.0
    delay_cost = total_delay * 150.0
    total_cost = cancellation_cost + delay_cost

    scores = score_plan(
        delay_minutes=total_delay,
        missed_connections=12 if action_type == "cancel" else (4 if total_delay > 120 else 0),
        total_cost=total_cost,
        crew_buffer_penalty=0.0
    )

    plan = {
        "baseline": "GreedyRecovery",
        "plan_id": f"GREEDY-{uuid4().hex[:4].upper()}",
        "action_type": action_type,
        "plan_diff": plan_diff,
        "scores": scores,
        "raw_cost_inr": total_cost,
        "delay_minutes": total_delay
    }

    return plan
