"""
Integration tests for the LangGraph vertical slice workflow.
Verifies bounded loops, hard vetoes, counter-proposals, and escalation.
"""

from datetime import datetime, timedelta
from pathlib import Path

from skymediator.config import settings
from skymediator.graph import build_recovery_graph


def test_successful_recovery_single_round(tmp_path: Path):
    graph = build_recovery_graph()
    base_time = datetime(2026, 11, 1, 6, 0)

    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": (base_time + timedelta(hours=1)).isoformat(),
            "sta": (base_time + timedelta(hours=3, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    # Rested crew: duty started recently, FDP is well within 12.5h
    crew_roster = [
        {
            "crew_id": "CREW-RESTED",
            "duty_record": {"duty_start": base_time.isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": (base_time + timedelta(hours=1)).isoformat(),
            "window_end": (base_time + timedelta(hours=1, minutes=30)).isoformat(),
            "capacity": 10
        }
    ]

    initial_state = {
        "run_id": "TEST-SUCCESS-01",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "affected_flight_id": "6E-101",
            "candidate_tail": "VT-BLR15"
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster,
        "slot_windows": slot_windows
    }

    final_state = graph.invoke(initial_state)

    assert final_state["status"] == "AWAITING_APPROVAL"
    assert final_state["selected_plan"] is not None
    assert final_state["round"] == 1
    assert len(final_state["candidates"]) == 1
    assert final_state["selected_plan"]["is_feasible"] is True


def test_hard_veto_with_counter_proposal_loop(tmp_path: Path):
    graph = build_recovery_graph()
    base_time = datetime(2026, 11, 1, 6, 0)

    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": base_time.isoformat(),
            "sta": (base_time + timedelta(hours=2, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    # Pilot started at 02:00 AM (WOCL encroachment -> max FDP is 660 mins / 11.0 hours)
    crew_roster = [
        {
            "crew_id": "CREW-WOCL-01",
            "duty_record": {"duty_start": datetime(2026, 11, 1, 2, 0).isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": base_time.isoformat(),
            "window_end": (base_time + timedelta(hours=8)).isoformat(),
            "capacity": 20
        }
    ]

    initial_state = {
        "run_id": "TEST-COUNTER-02",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "affected_flight_id": "6E-101",
            "initial_action": "excessive_delay",
            "delay_minutes": 320,  # 320m delay pushes arrival to 13:50 + 15m = 14:05 -> FDP = 725m > 660m -> VETO!
            "counter_delay_minutes": 30  # Counter-proposal: 30m delay -> arrival 09:00 + 15m = 09:15 -> FDP = 435m <= 660m -> PASS!
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster,
        "slot_windows": slot_windows
    }

    final_state = graph.invoke(initial_state)

    # Round 1 was VETOED by Crew Legality
    assert len(final_state["candidates"]) >= 2
    round_1_candidate = final_state["candidates"][0]
    assert "crew" in round_1_candidate["vetoed_by"]
    assert "Flight Duty Period" in round_1_candidate["veto_reasons"]["crew"] or "FDP" in round_1_candidate["veto_reasons"]["crew"]

    # Round 2 counter-proposal succeeded
    assert final_state["status"] == "AWAITING_APPROVAL"
    selected = final_state["selected_plan"]
    assert selected is not None
    assert selected["round_created"] == 2
    assert "crew" not in selected.get("vetoed_by", [])
    assert selected["is_feasible"] is True


def test_max_rounds_escalation():
    graph = build_recovery_graph()
    base_time = datetime(2026, 11, 1, 5, 0)

    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": (base_time + timedelta(hours=1)).isoformat(),
            "sta": (base_time + timedelta(hours=3, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    # Extreme duty: pilot started 16 hours ago (impossible to legally fly any flight)
    crew_roster = [
        {
            "crew_id": "CREW-PERMANENTLY-ILLEGAL",
            "duty_record": {"duty_start": (base_time - timedelta(hours=16)).isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    # Zero slot capacity
    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": (base_time + timedelta(hours=1)).isoformat(),
            "window_end": (base_time + timedelta(hours=1, minutes=30)).isoformat(),
            "capacity": 0
        }
    ]

    initial_state = {
        "run_id": "TEST-ESCALATION-03",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "affected_flight_id": "6E-101",
            "candidate_tail": "VT-BLR15"
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster,
        "slot_windows": slot_windows
    }

    final_state = graph.invoke(initial_state)

    # All rounds failed -> ESCALATED
    assert final_state["status"] == "ESCALATED"
    assert final_state["selected_plan"] is None
    assert "All candidate plans were vetoed" in final_state["escalation_reason"]
