"""
Baseline A: Greedy Rule-Based Disruption Recovery.
Implements a standard sequential heuristic prioritizing scheduled departure over
statutory crew legality and movement slots, reflecting conventional airline practices.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from skymediator.models import DelayOp, SwapTailOp, CancelOp
from skymediator.tools.scoring import score_plan
from skymediator.tools.schedule import apply_plan_diff


def run_greedy_baseline(
    disruption: Dict[str, Any],
    base_schedule: List[Dict[str, Any]],
    active_crew: Optional[List[Dict[str, Any]]] = None,
    slot_windows: Optional[List[Dict[str, Any]]] = None,
    max_delay_threshold_min: int = 240
) -> Dict[str, Any]:
    """
    Executes a greedy recovery strategy:
    1. If AOG: Swaps to available standby tail VT-BLR15; if unavailable, cancels.
    2. If Fog / Delay: Applies full uncalibrated delay up to max_delay_threshold_min (240m).
       If delay exceeds 240m, cancels the flight.
    3. Blind to crew FDTL limits and slot capacities (leading to violations under severe conditions).
    """
    affected_id = disruption.get("affected_flight_id", "6E-101")
    dis_type = (disruption.get("disruption_type") or disruption.get("type") or "fog").lower()
    raw_delay = int(disruption.get("delay_minutes", 180))
    target_flight = next((f for f in base_schedule if f["flight_id"] == affected_id), None)

    if not target_flight:
        return {
            "status": "FAILED",
            "reason": f"Flight {affected_id} not found in base schedule",
            "plan_diff": [],
            "scores": {"composite_score": 1.0, "raw_metrics": {"total_cost": 500000.0, "delay_minutes": 300.0}}
        }

    std_dt = datetime.fromisoformat(target_flight["std"])
    sta_dt = datetime.fromisoformat(target_flight["sta"])
    plan_diff: List[Dict[str, Any]] = []

    if "aog" in dis_type or disruption.get("initial_action") == "swap_tail":
        target_tail = disruption.get("candidate_tail", "VT-BLR15")
        plan_diff = [
            SwapTailOp(
                flight_id=affected_id,
                original_tail=target_flight["tail"],
                new_tail=target_tail,
                reason="Greedy heuristic: Swap to first available idle tail"
            ).model_dump()
        ]
    elif raw_delay > max_delay_threshold_min or disruption.get("initial_action") == "cancel":
        plan_diff = [
            CancelOp(
                flight_id=affected_id,
                reason=f"Greedy heuristic: Delay of {raw_delay}m exceeds 240m threshold; cancel flight"
            ).model_dump()
        ]
    else:
        # Greedily allocate full operational delay without checking pilot FDP limits
        alloc_delay = max(15, raw_delay)
        plan_diff = [
            DelayOp(
                flight_id=affected_id,
                delay_minutes=alloc_delay,
                new_std=std_dt + timedelta(minutes=alloc_delay),
                new_sta=sta_dt + timedelta(minutes=alloc_delay),
                reason=f"Greedy heuristic: Allocate raw operational delay of {alloc_delay}m"
            ).model_dump()
        ]

    candidate_plan = {
        "plan_id": f"PLAN-GREEDY-{uuid4().hex[:4]}",
        "proposing_agent": "GreedyHeuristic",
        "plan_diff": plan_diff,
        "operational_rationale": "Greedy sequential allocation prioritizing departure over crew/slot constraints."
    }

    # Evaluate deterministic multi-objective scores
    d_mins = float(raw_delay if (plan_diff and plan_diff[0].get("op") == "delay") else 0.0)
    is_cancel = plan_diff and plan_diff[0].get("op") == "cancel"
    is_swap = plan_diff and plan_diff[0].get("op") == "swap_tail"
    c_cost = 250000.0 if is_cancel else (15000.0 if is_swap else d_mins * 600.0)
    m_conn = 15 if is_cancel else (6 if d_mins > 60 else 0)

    scores = score_plan(
        delay_minutes=d_mins,
        missed_connections=m_conn,
        total_cost=c_cost,
        crew_buffer_penalty=0.0
    )
    scores["raw_metrics"] = {
        "total_cost": c_cost,
        "delay_minutes": d_mins,
        "missed_connections": m_conn,
        "affected_passengers": m_conn * 2
    }
    candidate_plan["scores"] = scores
    return candidate_plan
