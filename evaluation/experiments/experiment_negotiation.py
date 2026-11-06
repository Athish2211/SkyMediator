"""
Experiment 3: One Negotiation Round vs Three Negotiation Rounds (RQ3).
Measures plan quality, hard-veto resolution rate, recovery cost, and deliberation latency
when negotiation rounds are restricted to 1 round vs the full 3-round bounded consensus.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from typing import Any, Dict, List

from skymediator.graph import build_recovery_graph
from evaluation.metrics.calculate_metrics import evaluate_plan_compliance_and_cost


def run_negotiation_rounds_experiment(
    scenarios: List[Dict[str, Any]],
    repetitions: int = 1
) -> List[Dict[str, Any]]:
    """Runs Experiment 3: 1 Round vs 3 Rounds Deliberation across scenarios."""
    results: List[Dict[str, Any]] = []
    graph = build_recovery_graph()

    for rep in range(1, repetitions + 1):
        for scen in scenarios:
            scen_id = scen["scenario_id"]
            base_time = datetime.fromisoformat(scen["start_time"])
            affected_id = scen.get("affected_flight_id", "6E-101")
            dis_type = scen.get("disruption_type", "fog")

            base_schedule = [
                {
                    "flight_id": affected_id,
                    "tail": "VT-BLR01",
                    "origin": scen["airport"],
                    "dest": "VIDP",
                    "std": base_time.isoformat(),
                    "sta": (base_time + timedelta(hours=2, minutes=30)).isoformat(),
                    "seats": 180,
                    "status": "SCHEDULED"
                }
            ]

            d_start_str = scen.get("crew_duty_start")
            d_start = datetime.fromisoformat(d_start_str) if d_start_str else (base_time - timedelta(hours=2))
            crew_roster = [
                {
                    "crew_id": "CREW-EX-01",
                    "duty_start": d_start.isoformat(),
                    "duty_record": {"duty_start": d_start.isoformat()},
                    "assigned_flights": [affected_id]
                }
            ]

            slot_windows = [
                {
                    "airport": scen["airport"],
                    "window_start": base_time.isoformat(),
                    "window_end": (base_time + timedelta(hours=8)).isoformat(),
                    "capacity": int(scen.get("slot_capacity", 12))
                }
            ]

            disruption_spec = {
                "scenario_id": scen_id,
                "type": dis_type,
                "airport": scen["airport"],
                "affected_flight_id": affected_id,
                "initial_action": scen.get("initial_action", "delay"),
                "delay_minutes": scen.get("delay_minutes", 60),
                "counter_delay_minutes": scen.get("counter_delay_minutes", 30),
                "candidate_tail": scen.get("candidate_tail", "VT-BLR15")
            }

            # 1. Condition 1: Single Round Only (max_rounds = 1)
            t0 = time.perf_counter()
            state_r1 = {
                "run_id": f"NEG1-{scen_id}-{rep}",
                "max_rounds": 1,
                "disruption": disruption_spec,
                "base_schedule": base_schedule,
                "active_crew": crew_roster,
                "slot_windows": slot_windows
            }
            res_r1 = graph.invoke(state_r1)
            lat_r1 = time.perf_counter() - t0
            sel_r1 = res_r1.get("selected_plan") or {
                "plan_id": "ESCALATED_R1",
                "scores": {"composite_score": 1.0, "raw_metrics": {"total_cost": 500000.0, "delay_minutes": 320.0}},
                "plan_diff": [],
                "vetoed_by": ["compliance"]
            }
            eval_r1 = evaluate_plan_compliance_and_cost(sel_r1, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "negotiation_rounds",
                "scenario_id": scen_id,
                "repetition": rep,
                "rounds_setting": "1 Round (No Negotiation)",
                "actual_rounds": 1,
                "status": res_r1.get("status"),
                "latency_s": round(lat_r1, 3),
                "total_cost_inr": eval_r1["total_cost_inr"],
                "delay_minutes": eval_r1["delay_minutes"],
                "composite_score": eval_r1["composite_score"],
                "is_feasible": eval_r1["is_feasible"],
                "vetoed": len(sel_r1.get("vetoed_by", [])) > 0
            })

            # 2. Condition 2: Full 3 Rounds (max_rounds = 3)
            t0 = time.perf_counter()
            state_r3 = {
                "run_id": f"NEG3-{scen_id}-{rep}",
                "max_rounds": 3,
                "disruption": disruption_spec,
                "base_schedule": base_schedule,
                "active_crew": crew_roster,
                "slot_windows": slot_windows
            }
            res_r3 = graph.invoke(state_r3)
            lat_r3 = time.perf_counter() - t0
            sel_r3 = res_r3.get("selected_plan") or {
                "plan_id": "ESCALATED_R3",
                "scores": {"composite_score": 1.0, "raw_metrics": {"total_cost": 500000.0, "delay_minutes": 320.0}},
                "plan_diff": [],
                "vetoed_by": ["compliance"]
            }
            eval_r3 = evaluate_plan_compliance_and_cost(sel_r3, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "negotiation_rounds",
                "scenario_id": scen_id,
                "repetition": rep,
                "rounds_setting": "3 Rounds (Iterative Deliberation)",
                "actual_rounds": res_r3.get("round", 1),
                "status": res_r3.get("status"),
                "latency_s": round(lat_r3, 3),
                "total_cost_inr": eval_r3["total_cost_inr"],
                "delay_minutes": eval_r3["delay_minutes"],
                "composite_score": eval_r3["composite_score"],
                "is_feasible": eval_r3["is_feasible"],
                "vetoed": len(sel_r3.get("vetoed_by", [])) > 0
            })

    return results

