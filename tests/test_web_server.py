"""
Unit and API integration tests for the SkyMediator OCC Web Dashboard server.
"""

from fastapi.testclient import TestClient
from skymediator.app.server import app
from skymediator.config import settings
from skymediator.fixtures import seed_database
from skymediator.ingest.make_scenarios import seed_scenarios

# Seed test database with all scenarios
seed_database(settings.DB_PATH)
seed_scenarios(settings.DB_PATH)

client = TestClient(app)


def test_get_dashboard_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SkyMediator OCC" in response.text
    assert "VOBL" in response.text


def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["primary_hub"] == "VOBL"
    assert data["primary_iata"] == "BLR"
    assert data["status"] == "OPERATIONAL"


def test_api_scenarios():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 3


def test_api_flights():
    response = client.get("/api/flights")
    assert response.status_code == 200
    data = response.json()
    assert "flights" in data


def test_api_run_recovery_and_approve():
    # Trigger recovery for Scenario 2 (Severe Fog)
    trigger_res = client.post(
        "/api/run_recovery",
        json={"scenario_id": "SCENARIO_02_SEVERE_CAT3_FOG"}
    )
    assert trigger_res.status_code == 200
    rec_data = trigger_res.json()
    assert "run_id" in rec_data
    assert "candidates" in rec_data
    assert len(rec_data["candidates"]) >= 1

    run_id = rec_data["run_id"]

    # Submit Duty Manager Approval
    approve_res = client.post(
        "/api/approve_plan",
        json={
            "run_id": run_id,
            "decision": "APPROVE",
            "selected_plan_id": rec_data.get("selected_plan", {}).get("plan_id"),
            "manager_notes": "Tactical approval authorized."
        }
    )
    assert approve_res.status_code == 200
    appr_data = approve_res.json()
    assert appr_data["status"] == "APPROVED"
