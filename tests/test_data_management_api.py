"""
Unit tests for SkyMediator Predefined Operational Data Management APIs:
Fleet, Schedule, Crew Duties, Scenarios CRUD, and Database Reset.
"""

import pytest
from fastapi.testclient import TestClient
from skymediator.app.server import app
from skymediator.config import settings
from skymediator.fixtures import seed_database


@pytest.fixture(autouse=True)
def fresh_test_db(tmp_path, monkeypatch):
    """Isolate each test with a pristine temporary SQLite database."""
    test_db = tmp_path / "test_data_mgmt.db"
    seed_database(test_db)
    from skymediator.ingest.make_scenarios import seed_scenarios
    seed_scenarios(test_db)
    monkeypatch.setattr(settings, "DB_PATH", test_db)
    return test_db


@pytest.fixture
def client():
    return TestClient(app)


def test_get_llm_status(client):
    """Tests the /api/llm_status endpoint returns expected structure."""
    resp = client.get("/api/llm_status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "model" in data
    assert "provider" in data


def test_fleet_crud_endpoints(client):
    """Tests listing, adding, and deleting aircraft from the fleet."""
    # 1. List initial fleet
    resp = client.get("/api/fleet")
    assert resp.status_code == 200
    initial_fleet = resp.json()["fleet"]
    assert len(initial_fleet) >= 15

    # 2. Add a new aircraft
    new_tail = "VT-TEST99"
    payload = {
        "tail": new_tail,
        "subfleet": "A320neo",
        "seat_capacity": 186,
        "maint_hours_remaining": 55.0,
        "turnaround_buffer_mins": 40
    }
    create_resp = client.post("/api/fleet", json=payload)
    assert create_resp.status_code == 200
    assert create_resp.json()["status"] == "SUCCESS"

    # Verify added
    resp_after = client.get("/api/fleet")
    tails = [a["tail"] for a in resp_after.json()["fleet"]]
    assert new_tail in tails

    # 3. Delete aircraft
    del_resp = client.delete(f"/api/fleet/{new_tail}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SUCCESS"

    # Verify deleted
    resp_final = client.get("/api/fleet")
    final_tails = [a["tail"] for a in resp_final.json()["fleet"]]
    assert new_tail not in final_tails


def test_schedule_crud_endpoints(client):
    """Tests listing, adding/updating, and deleting scheduled flights."""
    # 1. List schedule
    resp = client.get("/api/schedule")
    assert resp.status_code == 200
    assert resp.json()["flights_count"] >= 10

    # 2. Add a custom flight
    flight_payload = {
        "flight_id": "6E-9999",
        "tail": "VT-BLR01",
        "origin": "VOBL",
        "dest": "VABB",
        "std": "2026-11-01T12:00:00",
        "sta": "2026-11-01T13:45:00",
        "seats": 180,
        "status": "SCHEDULED"
    }
    create_resp = client.post("/api/schedule", json=flight_payload)
    assert create_resp.status_code == 200
    assert create_resp.json()["status"] == "SUCCESS"

    # Verify flight exists in schedule
    resp_after = client.get("/api/schedule")
    ids = [f["flight_id"] for f in resp_after.json()["flights"]]
    assert "6E-9999" in ids

    # 3. Delete custom flight
    del_resp = client.delete("/api/schedule/6E-9999")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SUCCESS"

    resp_final = client.get("/api/schedule")
    final_ids = [f["flight_id"] for f in resp_final.json()["flights"]]
    assert "6E-9999" not in final_ids


def test_crew_duties_management(client):
    """Tests reading crew rosters and updating crew duty start times."""
    # 1. List crew
    resp = client.get("/api/crew")
    assert resp.status_code == 200
    crew_list = resp.json()["crew"]
    assert len(crew_list) > 0

    # 2. Update duty start time to simulate WOCL night duty
    duty_payload = {
        "crew_id": "CREW-CAPT-01",
        "duty_start": "2026-11-01T02:00:00",
        "assigned_flight_id": "6E-101"
    }
    update_resp = client.post("/api/crew/duty", json=duty_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "SUCCESS"

    # Verify updated duty start
    resp_after = client.get("/api/crew")
    capt = next(c for c in resp_after.json()["crew"] if c["crew_id"] == "CREW-CAPT-01")
    assert capt["duty_start"] == "2026-11-01T02:00:00"
    assert capt["assigned_flight_id"] == "6E-101"


def test_scenarios_crud_endpoints(client):
    """Tests listing, adding, and deleting disruption scenarios."""
    # 1. List scenarios
    resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()["scenarios"]
    assert len(scenarios) >= 5

    # 2. Add custom scenario
    scen_payload = {
        "scenario_id": "SCEN_TEST_CUSTOM",
        "name": "Custom Test Disruption",
        "disruption_type": "fog",
        "airport": "VOBL",
        "severity": "SEVERE",
        "difficulty": "HARD",
        "start_time": "2026-11-01T05:00:00",
        "seeded_anomalies": {"affected_flight_id": "6E-101", "delay_minutes": 200}
    }
    create_resp = client.post("/api/scenarios", json=scen_payload)
    assert create_resp.status_code == 200
    assert create_resp.json()["status"] == "SUCCESS"

    # Verify scenario exists
    resp_after = client.get("/api/scenarios")
    scen_ids = [s["scenario_id"] for s in resp_after.json()["scenarios"]]
    assert "SCEN_TEST_CUSTOM" in scen_ids

    # 3. Delete scenario
    del_resp = client.delete("/api/scenarios/SCEN_TEST_CUSTOM")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SUCCESS"

    resp_final = client.get("/api/scenarios")
    final_ids = [s["scenario_id"] for s in resp_final.json()["scenarios"]]
    assert "SCEN_TEST_CUSTOM" not in final_ids


def test_database_reset_endpoint(client):
    """Tests resetting database to baseline seeded fixtures."""
    # Mutate schedule by deleting a flight
    client.delete("/api/schedule/6E-101")
    resp_mutated = client.get("/api/schedule")
    assert "6E-101" not in [f["flight_id"] for f in resp_mutated.json()["flights"]]

    # Call reset
    reset_resp = client.post("/api/database/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "SUCCESS"

    # Verify baseline restored
    resp_restored = client.get("/api/schedule")
    assert "6E-101" in [f["flight_id"] for f in resp_restored.json()["flights"]]
