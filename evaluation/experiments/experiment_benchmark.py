"""
Experiment 6: Benchmark Solver Comparison (RQ5).
Compares SkyMediator (7-Agent Deliberation) against:
1. Greedy Rule-Based Recovery Baseline
2. Google OR-Tools Mathematical Optimization Solver
across operational cost, delay minutes, passenger impact, and independent FDTL legality.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from typing import Any, Dict, List

from skymediator.graph import build_recovery_graph
from evaluation.baselines.greedy_baseline import run_greedy_baseline
from evaluation.baselines.ortools_baseline import run_ortools_baseline
from evaluation.metrics.calculate_metrics import evaluate_plan_compliance_and_cost


def run_benchmark_experiment(
    scenarios: List[Dict[str, Any]],
    repetitions: int = 1
) -> List[Dict[str, Any]]:
    """Runs comparative benchmarks across all compatible scenarios."""
    results: List[Dict[str, Any]] = []
    graph = build_recovery_graph()

    compatible_scenarios = [s for s in scenarios if not s.get("trigger_abstention")]

    for rep in range(1, repetitions + 1):
        for scen in compatible_scenarios:
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

            # 1. SkyMediator Multi-Agent System
            t0 = time.perf_counter()
            ma_state = {
                "run_id": f"BENCH-MA-{scen_id}-{rep}",
                "disruption": disruption_spec,
                "base_schedule": base_schedule,
                "active_crew": crew_roster,
                "slot_windows": slot_windows
            }
            res_ma = graph.invoke(ma_state)
            lat_ma = time.perf_counter() - t0
            sel_ma = res_ma.get("selected_plan") or {
                "plan_id": "ESCALATED",
                "scores": {"composite_score": 1.0, "raw_metrics": {"total_cost": 500000.0, "delay_minutes": 320.0}},
                "plan_diff": [],
                "vetoed_by": ["compliance"]
            }
            eval_ma = evaluate_plan_compliance_and_cost(sel_ma, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "benchmark_comparison",
                "scenario_id": scen_id,
                "repetition": rep,
                "system": "SkyMediator (Multi-Agent)",
                "latency_s": round(lat_ma, 3),
                "total_cost_inr": eval_ma["total_cost_inr"],
                "delay_minutes": eval_ma["delay_minutes"],
                "pax_disrupted": eval_ma["pax_disrupted"],
                "composite_score": eval_ma["composite_score"],
                "is_feasible": eval_ma["is_feasible"],
                "fdtl_violations": eval_ma["fdtl_violations_count"],
                "slot_violations": eval_ma["slot_violations_count"]
            })

            # 2. Greedy Recovery Baseline
            t0 = time.perf_counter()
            res_gr = run_greedy_baseline(disruption_spec, base_schedule, active_crew=crew_roster, slot_windows=slot_windows)
            lat_gr = time.perf_counter() - t0
            eval_gr = evaluate_plan_compliance_and_cost(res_gr, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "benchmark_comparison",
                "scenario_id": scen_id,
                "repetition": rep,
                "system": "Greedy Recovery Heuristic",
                "latency_s": round(lat_gr, 3),
                "total_cost_inr": eval_gr["total_cost_inr"],
                "delay_minutes": eval_gr["delay_minutes"],
                "pax_disrupted": eval_gr["pax_disrupted"],
                "composite_score": eval_gr["composite_score"],
                "is_feasible": eval_gr["is_feasible"],
                "fdtl_violations": eval_gr["fdtl_violations_count"],
                "slot_violations": eval_gr["slot_violations_count"]
            })

            # 3. Google OR-Tools Solver Baseline
            t0 = time.perf_counter()
            res_opt = run_ortools_baseline(disruption_spec, base_schedule, active_crew=crew_roster, slot_windows=slot_windows)
            lat_opt = time.perf_counter() - t0
            eval_opt = evaluate_plan_compliance_and_cost(res_opt, base_schedule, crew_roster, slot_windows)

            results.append({
                "experiment": "benchmark_comparison",
                "scenario_id": scen_id,
                "repetition": rep,
                "system": "Google OR-Tools Solver",
                "latency_s": round(lat_opt, 3),
                "total_cost_inr": eval_opt["total_cost_inr"],
                "delay_minutes": eval_opt["delay_minutes"],
                "pax_disrupted": eval_opt["pax_disrupted"],
                "composite_score": eval_opt["composite_score"],
                "is_feasible": eval_opt["is_feasible"],
                "fdtl_violations": eval_opt["fdtl_violations_count"],
                "slot_violations": eval_opt["slot_violations_count"]
            })

    return results

