"""
Unit tests for Baselines (Greedy & Optimization Solver) and Evaluation Harness.
Verifies Task T-7.1, T-7.2, T-8.1 and Gate 5 criteria.
"""

from datetime import datetime, timedelta
import pytest

from skymediator.config import settings
from skymediator.eval.baselines.greedy_recovery import run_greedy_recovery
from skymediator.eval.baselines.or_tools_solver import run_optimization_solver
from skymediator.eval.metrics import compute_scenario_metrics, aggregate_benchmark_metrics
from skymediator.eval.run_eval import run_full_benchmark


@pytest.fixture
def sample_schedule():
    now = datetime(2026, 11, 1, 6, 0)
    return [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": now.isoformat(),
            "sta": (now + timedelta(hours=2, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]


def test_greedy_recovery_baseline(sample_schedule):
    disruption = {
        "affected_flight_id": "6E-101",
        "type": "fog",
        "delay_minutes": 180
    }
    res = run_greedy_recovery(disruption, sample_schedule)
    assert res["baseline"] == "GreedyRecovery"
    assert len(res["plan_diff"]) > 0
    assert res["scores"]["composite_score"] >= 0.0


def test_optimization_solver_baseline(sample_schedule):
    disruption = {
        "affected_flight_id": "6E-101",
        "type": "fog",
        "delay_minutes": 180,
        "candidate_tail": "VT-BLR15"
    }
    crew = [
        {
            "crew_id": "CREW-01",
            "duty_record": {"duty_start": datetime(2026, 11, 1, 5, 0).isoformat()}
        }
    ]
    res = run_optimization_solver(disruption, sample_schedule, active_crew=crew)
    assert res["baseline"] == "OptimizationSolver"
    assert res["status"] == "OPTIMAL"
    assert len(res["plan_diff"]) > 0
    assert 0.0 <= res["scores"]["composite_score"] <= 1.0


def test_metrics_calculation(sample_schedule):
    plan = {
        "plan_id": "TEST-PLAN-01",
        "scores": {"composite_score": 0.05, "raw_metrics": {"total_cost": 4500.0, "delay_minutes": 30.0}},
        "is_feasible": True
    }
    crew = [
        {
            "crew_id": "CREW-01",
            "duty_start": datetime(2026, 11, 1, 5, 0).isoformat(),
            "assigned_flights": ["6E-101"]
        }
    ]
    metrics = compute_scenario_metrics(plan, sample_schedule, crew)
    assert metrics["plan_id"] == "TEST-PLAN-01"
    assert metrics["fdtl_compliant"] is True
    assert metrics["composite_score"] == 0.05

    agg = aggregate_benchmark_metrics([metrics])
    assert agg["total_scenarios"] == 1
    assert agg["fdtl_violation_rate_pct"] == 0.0
    assert agg["fdtl_perfect_compliance"] is True


def test_run_full_benchmark_harness():
    results = run_full_benchmark(limit_scenarios=2)
    assert "multi_agent" in results
    assert "greedy_baseline" in results
    assert "optimization_solver" in results
    assert results["scenarios_evaluated"] == 2
    # Verify Multi-Agent achieves 0.00% FDTL violations
    assert results["multi_agent"]["fdtl_violation_rate_pct"] == 0.0
