"""
Unit tests for Duty Manager natural language message parsing and multi-agent triggering.
Tests the Mediator LLM disruption comprehension agent and graph integration.
"""

from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from skymediator.config import settings
from skymediator.graph import build_recovery_graph
from skymediator.llm import parse_duty_manager_disruption
from skymediator.app.server import app


def test_parse_fog_disruption_message():
    msg = (
        "Dense CAT III radiation fog at Kempegowda BLR (RVR < 250m). "
        "Flight 6E-101 holding with estimated 180 min delay. Assess tail swap to VT-BLR15 or tactical delay."
    )
    parsed = parse_duty_manager_disruption(msg)
    assert parsed["disruption_type"] == "fog"
    assert parsed["airport"] == "VOBL"
    assert parsed["affected_flight_id"] == "6E-101"
    assert parsed["severity"] == "SEVERE"
    assert parsed["delay_minutes"] == 180
    assert parsed["candidate_tail"] == "VT-BLR15"
    assert "tactical_summary" in parsed


def test_parse_aog_hydraulic_snag_message():
    msg = (
        "VT-BLR01 grounded at Kempegowda BLR due to hydraulic leak snag on flight 6E-205. "
        "AOG for 4 hours. Recommend aircraft swap to standby VT-BLR15."
    )
    parsed = parse_duty_manager_disruption(msg)
    assert parsed["disruption_type"] == "aog"
    assert parsed["airport"] == "VOBL"
    assert parsed["affected_flight_id"] == "6E-205"
    assert parsed["initial_action"] == "swap_tail"
    assert parsed["candidate_tail"] == "VT-BLR15"
    assert parsed["delay_minutes"] == 240  # 4 hours


def test_parse_crew_duty_exceedance_message():
    msg = (
        "Flight 6E-302 pilot duty exceedance risk. Captain on 02:00 AM WOCL duty will violate "
        "11.0h max FDP under 120m holding delay at Delhi VIDP."
    )
    parsed = parse_duty_manager_disruption(msg)
    assert parsed["disruption_type"] == "crew"
    assert parsed["airport"] == "VIDP"
    assert parsed["affected_flight_id"] == "6E-302"
    assert parsed["delay_minutes"] == 120


def test_parse_slot_curfew_message():
    msg = (
        "Runway 09/27 maintenance closure at BLR for 2 hours. Slot movements restricted to 8 per window. "
        "Flight 6E-101 departure delayed by 90m."
    )
    parsed = parse_duty_manager_disruption(msg)
    assert parsed["disruption_type"] == "slot"
    assert parsed["affected_flight_id"] == "6E-101"
    assert parsed["delay_minutes"] == 90


def test_parse_cancel_directive_message():
    msg = "Strategic cancellation required for flight 6E-501 due to airport curfew."
    parsed = parse_duty_manager_disruption(msg)
    assert parsed["affected_flight_id"] == "6E-501"
    assert parsed["initial_action"] == "cancel"


def test_graph_execution_from_duty_manager_message():
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
    crew_roster = [
        {
            "crew_id": "CREW-CAPT-01",
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

    dm_message = (
        "Kempegowda BLR ground reports dense radiation fog dropping runway visual range below 250m. "
        "Flight 6E-101 is holding with estimated 180 min delay. Assess aircraft tail swap to VT-BLR15."
    )

    state = {
        "run_id": "TEST-NL-01",
        "duty_manager_message": dm_message,
        "base_schedule": base_schedule,
        "active_crew": crew_roster,
        "slot_windows": slot_windows
    }

    final_state = graph.invoke(state)
    assert final_state["status"] in ["AWAITING_APPROVAL", "ESCALATED"]
    assert final_state.get("parsed_disruption") is not None
    assert final_state["parsed_disruption"]["affected_flight_id"] == "6E-101"
    assert len(final_state.get("candidates", [])) > 0


def test_api_parse_message_endpoint():
    client = TestClient(app)
    response = client.post(
        "/api/parse_message",
        json={"message": "Severe fog at BLR Kempegowda, flight 6E-101 delayed by 180 minutes"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PARSED"
    assert data["parsed_disruption"]["disruption_type"] == "fog"
    assert data["parsed_disruption"]["affected_flight_id"] == "6E-101"
    assert data["parsed_disruption"]["delay_minutes"] == 180


def test_api_run_recovery_with_duty_manager_message():
    client = TestClient(app)
    payload = {
        "duty_manager_message": (
            "Dense CAT III radiation fog at Kempegowda BLR (RVR < 250m). "
            "Flight 6E-101 holding with estimated 180 min delay."
        )
    }
    response = client.post("/api/run_recovery", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["AWAITING_APPROVAL", "ESCALATED"]
    assert data["parsed_disruption"] is not None
    assert data["parsed_disruption"]["affected_flight_id"] == "6E-101"
    assert len(data["candidates"]) >= 1
