"""
Baseline C: Monolithic Single-Agent Disruption Recovery.
Implements a single-agent approach where a single monolithic model/prompt
receives the full operational disruption context and formulates a single recovery plan
in a single pass, without specialist agent negotiation, multi-round consensus, or independent vetoes.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from skymediator.models import DelayOp, SwapTailOp, CancelOp
from skymediator.tools.scoring import score_plan
from skymediator.tools.schedule import apply_plan_diff


def run_single_agent_baseline(
    disruption: Dict[str, Any],
    base_schedule: List[Dict[str, Any]],
    active_crew: Optional[List[Dict[str, Any]]] = None,
    slot_windows: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Executes a monolithic single-agent recovery in a single shot.
    Lacks the 7-agent specialization, multi-round deliberation, and hard veto feedback loops.
    """
    affected_id = disruption.get("affected_flight_id", "6E-101")
    dis_type = (disruption.get("disruption_type") or disruption.get("type") or "fog").lower()
    raw_delay = int(disruption.get("delay_minutes", 120))
    target_flight = next((f for f in base_schedule if f["flight_id"] == affected_id), None)

    if not target_flight:
        return {
            "status": "FAILED",
            "reason": f"Flight {affected_id} not found in base schedule",
            "plan_diff": [],
            "scores": {"composite_score": 1.0}
        }

    std_dt = datetime.fromisoformat(target_flight["std"])
    sta_dt = datetime.fromisoformat(target_flight["sta"])
    plan_diff: List[Dict[str, Any]] = []

    # Single-agent heuristic / prompt logic:
    # Attempts to make a single trade-off decision without specialist counter-proposals
    candidate_tail = disruption.get("candidate_tail")
    is_aog = "aog" in dis_type

    if (is_aog or disruption.get("initial_action") == "swap_tail") and candidate_tail:
        # Single agent recognizes tail swap for AOG or swap directives
        plan_diff = [
            SwapTailOp(
                flight_id=affected_id,
                original_tail=target_flight["tail"],
                new_tail=candidate_tail,
                reason="Single-Agent decision: Aircraft swap to standby tail"
            ).model_dump()
        ]
        rationale = f"Single agent recommended tail swap to {candidate_tail}."
    elif raw_delay > 200 or disruption.get("initial_action") == "cancel":
        # Severe delay: single agent often chooses to cancel to avoid complexity,
        # missing subtle multi-agent crew repositioning or slot retiming alternatives
        plan_diff = [
            CancelOp(
                flight_id=affected_id,
                reason=f"Single-Agent decision: Heavy {raw_delay}m delay resolved via cancellation"
            ).model_dump()
        ]
        rationale = f"Single agent cancelled {affected_id} due to high delay severity."
    else:
        # Moderate delay: single agent applies heuristic delay without verifying WOCL or slot margins
        d_min = max(15, min(raw_delay, 60))
        plan_diff = [
            DelayOp(
                flight_id=affected_id,
                delay_minutes=d_min,
                new_std=std_dt + timedelta(minutes=d_min),
                new_sta=sta_dt + timedelta(minutes=d_min),
                reason=f"Single-Agent decision: Moderate {d_min}m operational delay"
            ).model_dump()
        ]
        rationale = f"Single agent applied {d_min}m delay to {affected_id}."

    candidate_plan = {
        "plan_id": f"PLAN-SINGLE-{uuid4().hex[:4]}",
        "proposing_agent": "SingleAgentMonolith",
        "plan_diff": plan_diff,
        "operational_rationale": rationale,
        "round_created": 1
    }

    is_cancel = plan_diff and plan_diff[0].get("op") == "cancel"
    is_swap = plan_diff and plan_diff[0].get("op") == "swap_tail"
    d_mins = float(plan_diff[0].get("delay_minutes", 0.0)) if (plan_diff and plan_diff[0].get("op") == "delay") else 0.0
    c_cost = 250000.0 if is_cancel else (15000.0 if is_swap else d_mins * 600.0)
    m_conn = 12 if is_cancel else (5 if d_mins > 60 else 0)

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
