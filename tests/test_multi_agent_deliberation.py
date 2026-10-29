"""
End-to-end integration tests for the full 7-Agent Deliberation Suite.
Verifies multi-agent interaction, reflection notes, parallel evaluation,
and structured trace logging in traces/.
"""

from datetime import datetime, timedelta
from pathlib import Path
from skymediator.config import settings
from skymediator.graph import build_recovery_graph


def test_full_7_agent_deliberation_flow():
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

    crew_roster = [
        {
            "crew_id": "CREW-CAPT-01",
            "duty_record": {"duty_start": base_time.isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": (base_time + timedelta(hours=1)).isoformat(),
            "window_end": (base_time + timedelta(hours=2)).isoformat(),
            "capacity": 15
        }
    ]

    initial_state = {
        "run_id": "E2E-7AGENT-01",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "severity": "MODERATE",
            "affected_flight_id": "6E-101",
            "candidate_tail": "VT-BLR15"
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster,
        "slot_windows": slot_windows
    }

    final_state = graph.invoke(initial_state)

    # 1. State must reach AWAITING_APPROVAL with a feasible plan
    assert final_state["status"] == "AWAITING_APPROVAL"
    selected = final_state["selected_plan"]
    assert selected is not None
    assert selected["is_feasible"] is True

    # 2. Sentinel forecast must be attached
    assert "sentinel_forecast" in final_state
    forecast = final_state["sentinel_forecast"]
    assert "probability" in forecast
    assert "recommended_action" in forecast

    # 3. Passenger and Cost evaluation reports must be present
    assert "passenger_reports" in final_state
    assert selected["plan_id"] in final_state["passenger_reports"]
    assert "cost_reports" in final_state
    assert selected["plan_id"] in final_state["cost_reports"]

    # 4. Mediator reflection notes must detail systemic trade-offs
    assert "reflection_notes" in final_state
    assert len(final_state["reflection_notes"]) > 0

    # 5. Verify trace logging to traces/ directory
    traces_dir = Path("traces")
    assert traces_dir.exists()
    trace_files = list(traces_dir.glob("*.jsonl"))
    assert len(trace_files) > 0
