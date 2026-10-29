"""
Unit tests for SkyMediator Pydantic models and PlanDiffOp discriminated unions.
"""

from datetime import datetime
import pytest
from pydantic import ValidationError

from skymediator.models import (
    Aircraft,
    Flight,
    SwapTailOp,
    DelayOp,
    CancelOp,
    RepositionCrewOp,
    CandidatePlan
)


def test_flight_model():
    f = Flight(
        flight_id="6E-101",
        tail="VT-BLR01",
        origin="VOBL",
        dest="VIDP",
        std=datetime(2026, 11, 1, 6, 0),
        sta=datetime(2026, 11, 1, 8, 30)
    )
    assert f.flight_id == "6E-101"
    assert f.status == "SCHEDULED"


def test_plan_diff_operations():
    op1 = SwapTailOp(
        flight_id="6E-101",
        original_tail="VT-BLR01",
        new_tail="VT-BLR15",
        reason="Standby swap"
    )
    assert op1.op == "swap_tail"

    op2 = DelayOp(
        flight_id="6E-101",
        delay_minutes=30,
        new_std=datetime(2026, 11, 1, 6, 30),
        new_sta=datetime(2026, 11, 1, 9, 0),
        reason="Fog clearance"
    )
    assert op2.op == "delay"

    op3 = CancelOp(
        flight_id="6E-102",
        reason="Slot saturation"
    )
    assert op3.op == "cancel"


def test_candidate_plan_feasibility():
    cand = CandidatePlan(
        plan_id="PLAN-001",
        round_created=1,
        proposing_agent="Rotation",
        plan_diff=[],
        operational_rationale="Test plan"
    )
    assert cand.is_feasible is True

    cand.vetoed_by.append("crew")
    assert cand.is_feasible is False
