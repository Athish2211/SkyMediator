"""
Unit tests for deterministic schedule tools and pure mutation logic (PROP-01).
"""

from datetime import datetime
from pathlib import Path

from skymediator.fixtures import seed_database
from skymediator.models import SwapTailOp, DelayOp, CancelOp
from skymediator.tools.schedule import apply_plan_diff, swap_tail, query_schedule


def test_apply_plan_diff_pure_mutation():
    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": "2026-11-01T06:00:00",
            "sta": "2026-11-01T08:30:00",
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    plan_diff = [
        SwapTailOp(
            flight_id="6E-101",
            original_tail="VT-BLR01",
            new_tail="VT-BLR15",
            reason="Swap test"
        ),
        DelayOp(
            flight_id="6E-101",
            delay_minutes=30,
            new_std=datetime(2026, 11, 1, 6, 30),
            new_sta=datetime(2026, 11, 1, 9, 0),
            reason="Delay test"
        )
    ]

    res = apply_plan_diff(base_schedule, plan_diff)
    assert res["applied_ops_count"] == 2
    assert len(res["unresolved_conflicts"]) == 0

    mutated = res["mutated_flights"][0]
    assert mutated["tail"] == "VT-BLR15"
    assert mutated["status"] == "DELAYED"
    assert mutated["etd"] == "2026-11-01T06:30:00"

    # Base schedule must remain completely unmutated (pure function)
    assert base_schedule[0]["tail"] == "VT-BLR01"
    assert base_schedule[0]["status"] == "SCHEDULED"


def test_swap_tail_turnaround_validation():
    schedule = [
        {
            "flight_id": "6E-201",
            "tail": "VT-BLR15",
            "origin": "VABB",
            "dest": "VOBL",
            "std": "2026-11-01T04:00:00",
            "sta": "2026-11-01T05:30:00",
            "status": "COMPLETED"
        },
        {
            "flight_id": "6E-202",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": "2026-11-01T06:15:00",
            "sta": "2026-11-01T08:45:00",
            "status": "SCHEDULED"
        }
    ]

    # VT-BLR15 arrives VOBL at 05:30. Flight 6E-202 departs VOBL at 06:15.
    # Turnaround = 45 minutes >= 35 min min_turn_min -> VALID!
    res = swap_tail("6E-202", "VT-BLR15", schedule, min_turn_min=35)
    assert res["is_valid"] is True
    assert res["turnaround_margin_minutes"] == 45

    # If min_turn_min is 50, it should be INVALID!
    res_tight = swap_tail("6E-202", "VT-BLR15", schedule, min_turn_min=50)
    assert res_tight["is_valid"] is False
    assert "Insufficient turnaround" in res_tight["reasons"][0]


def test_query_schedule(tmp_path: Path):
    db_file = tmp_path / "query_test.db"
    seed_database(db_file)

    flights = query_schedule(airport="VOBL", db_path=db_file)
    assert len(flights) > 0
    assert any(f["origin"] == "VOBL" or f["dest"] == "VOBL" for f in flights)
