"""
Experiment 1: Multi-Agent vs Single-Agent Architecture (RQ1 & RQ7).
Compares the full 7-agent deliberative SkyMediator system against the monolithic Single-Agent baseline
across operational cost, constraint compliance, passenger impact, delay propagation, latency, and token consumption.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from typing import Any, Dict, List

from skymediator.graph import build_recovery_graph
from evaluation.baselines.single_agent_baseline import run_single_agent_baseline
from evaluation.metrics.calculate_metrics import evaluate_plan_compliance_and_cost


def run_multi_agent_experiment(
    scenarios: List[Dict[str, Any]],
    repetitions: int = 1
) -> List[Dict[str, Any]]:
    """Runs Experiment 1: Single-Agent vs Multi-Agent across all scenarios."""
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
                "candidate_tail": scen.get("candidate_tail", "VT-BLR15"),
                "avoid_cancellation": scen.get("avoid_cancellation", False),
                "no_standby_aircraft": scen.get("no_standby_aircraft", False)
            }

            # 1. Full Multi-Agent Run
            t0 = time.perf_counter()
            ma_state = {
                "run_id": f"MA-{scen_id}-{rep}",
                "disruption": disruption_spec,
                "base_schedule": base_schedule,
                "active_crew": crew_roster,
                "slot_windows": slot_windows
            }
            res_ma = graph.invoke(ma_state)
            latency_ma = time.perf_counter() - t0
            selected_ma = res_ma.get("selected_plan") or {
                "plan_id": "ESCALATED",
                "scores": {"composite_score": 1.0, "raw_metrics": {"total_cost": 500000.0, "delay_minutes": 320.0}},
                "plan_diff": [],
                "vetoed_by": ["compliance"]
            }
            eval_ma = evaluate_plan_compliance_and_cost(selected_ma, base_schedule, crew_roster, slot_windows)
            rounds_ma = res_ma.get("round", 1)

            results.append({
                "experiment": "multi_agent_vs_single",
                "scenario_id": scen_id,
                "repetition": rep,
                "system": "SkyMediator (Multi-Agent)",
                "status": res_ma.get("status"),
                "rounds": rounds_ma,
                "latency_s": round(latency_ma, 3),
                "tokens_est": 1850 * rounds_ma,
                "total_cost_inr": eval_ma["total_cost_inr"],
                "delay_minutes": eval_ma["delay_minutes"],
                "pax_disrupted": eval_ma["pax_disrupted"],
                "composite_score": eval_ma["composite_score"],
                "is_feasible": eval_ma["is_feasible"],
                "fdtl_violations": eval_ma["fdtl_violations_count"],
                "slot_violations": eval_ma["slot_violations_count"]
            })

            # 2. Single-Agent Baseline Run
            t0 = time.perf_counter()
            res_sa = run_single_agent_baseline(disruption_spec, base_schedule, active_crew=crew_roster, slot_windows=slot_windows)
            latency_sa = time.perf_counter() - t0
            eval_sa = evaluate_plan_compliance_and_cost(res_sa, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "multi_agent_vs_single",
                "scenario_id": scen_id,
                "repetition": rep,
                "system": "Single-Agent Monolith",
                "status": "COMPLETED",
                "rounds": 1,
                "latency_s": round(latency_sa, 3),
                "tokens_est": 620,
                "total_cost_inr": eval_sa["total_cost_inr"],
                "delay_minutes": eval_sa["delay_minutes"],
                "pax_disrupted": eval_sa["pax_disrupted"],
                "composite_score": eval_sa["composite_score"],
                "is_feasible": eval_sa["is_feasible"],
                "fdtl_violations": eval_sa["fdtl_violations_count"],
                "slot_violations": eval_sa["slot_violations_count"]
            })

    return results

