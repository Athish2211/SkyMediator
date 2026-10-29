"""
Comprehensive OCC Stress & Operational Reliability Test Suite.
Tests:
1. PROP-04 Human Replan Feedback Loop (directive-based candidate regeneration).
2. Multi-Incident Disruption Stacking across multiple aircraft.
3. Strict Hard Veto Safety (FDTL/Slot vetoed plans cannot be approved).
4. High Concurrency & Thread-Safe Deliberation.
5. Full API End-to-End Pipeline Verification.
"""

import pytest
import concurrent.futures
from fastapi.testclient import TestClient
from skymediator.app.server import app, ACTIVE_DISRUPTIONS
from skymediator.config import settings
from skymediator.fixtures import reset_all_data


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure clean baseline database fixtures and reset disruption stack before each test."""
    reset_all_data(settings.DB_PATH)
    ACTIVE_DISRUPTIONS.clear()
    yield


def test_replan_feedback_loop_tail_swap():
    """Tests that requesting a replan with 'swap' directive synthesizes a SwapTailOp candidate."""
    client = TestClient(app)

    # 1. Trigger initial disruption (Fog on 6E-101)
    rec_res = client.post("/api/run_recovery", json={
        "duty_manager_message": "Dense fog at BLR delay 6E-101 by 180 mins"
    })
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    run_id = rec_data["run_id"]
    initial_plan_id = rec_data["selected_plan"]["plan_id"]
    initial_rounds = rec_data["rounds_executed"]

    # 2. Duty Manager issues Replan Directive: "Reassign tail to standby VT-BLR15"
    replan_res = client.post("/api/approve_plan", json={
        "run_id": run_id,
        "decision": "REPLAN",
        "selected_plan_id": initial_plan_id,
        "manager_notes": "Prioritize departure: Swap tail to standby VT-BLR15 immediately"
    })
    assert replan_res.status_code == 200
    replan_data = replan_res.json()
    assert replan_data["status"] in ("REVISION_REQUESTED", "REVISION_GENERATED")
    assert replan_data["selected_plan"] is not None
    new_plan = replan_data["selected_plan"]
    assert new_plan["plan_id"] != initial_plan_id
    assert new_plan["round_created"] >= 2

    # Verify SwapTailOp was synthesized
    ops = [op.get("op") for op in new_plan.get("plan_diff", [])]
    assert "swap_tail" in ops
    swap_op = next(op for op in new_plan["plan_diff"] if op.get("op") == "swap_tail")
    assert swap_op["new_tail"] == "VT-BLR15"
    assert swap_op["flight_id"] == "6E-101"


def test_replan_feedback_loop_cancel_directive():
    """Tests that requesting a replan with 'cancel' directive synthesizes a CancelOp candidate."""
    client = TestClient(app)

    # 1. Trigger initial disruption
    rec_res = client.post("/api/run_recovery", json={
        "duty_manager_message": "Operational snag on 6E-101"
    })
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    run_id = rec_data["run_id"]

    # 2. Duty Manager instructs cancellation
    replan_res = client.post("/api/approve_plan", json={
        "run_id": run_id,
        "decision": "REPLAN",
        "selected_plan_id": rec_data["selected_plan"]["plan_id"],
        "manager_notes": "No aircraft available, cancel flight 6E-101 per passenger reaccommodation protocol"
    })
    assert replan_res.status_code == 200
    replan_data = replan_res.json()
    assert replan_data["status"] in ("REVISION_REQUESTED", "REVISION_GENERATED")
    new_plan = replan_data["selected_plan"]
    ops = [op.get("op") for op in new_plan.get("plan_diff", [])]
    assert "cancel" in ops


def test_replan_feedback_loop_calibrated_delay():
    """Tests that requesting a replan with 'delay 45 mins' directive synthesizes a calibrated DelayOp."""
    client = TestClient(app)

    rec_res = client.post("/api/run_recovery", json={
        "duty_manager_message": "Snag on 6E-101 at VOBL"
    })
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    run_id = rec_data["run_id"]

    replan_res = client.post("/api/approve_plan", json={
        "run_id": run_id,
        "decision": "REPLAN",
        "selected_plan_id": rec_data["selected_plan"]["plan_id"],
        "manager_notes": "Aircraft serviceable soon: delay 45 minutes instead of swap"
    })
    assert replan_res.status_code == 200
    replan_data = replan_res.json()
    assert replan_data["status"] in ("REVISION_REQUESTED", "REVISION_GENERATED")
    new_plan = replan_data["selected_plan"]
    ops = [op.get("op") for op in new_plan.get("plan_diff", [])]
    assert "delay" in ops
    delay_op = next(op for op in new_plan["plan_diff"] if op.get("op") == "delay")
    assert delay_op["delay_minutes"] == 45


def test_disruption_stacking_multi_incident():
    """Tests that sequential disruptions stack into ACTIVE_DISRUPTIONS and produce multi-aircraft diffs."""
    client = TestClient(app)

    # 1. Report Disruption 1: Fog on 6E-101 at BLR
    res1 = client.post("/api/run_recovery", json={
        "duty_manager_message": "CAT III Fog at BLR delay 6E-101 by 60 mins"
    })
    assert res1.status_code == 200

    # Verify Disruption 1 is in stack
    stack1 = client.get("/api/disruptions").json()
    assert stack1["count"] == 1
    assert stack1["disruptions"][0]["affected_flight_id"] == "6E-101"

    # 2. Report Disruption 2: Hydraulic AOG on 6E-103
    res2 = client.post("/api/run_recovery", json={
        "duty_manager_message": "Hydraulic snag on 6E-103 at BOM, AOG reported"
    })
    assert res2.status_code == 200
    data2 = res2.json()

    # Verify both disruptions are stacked
    stack2 = client.get("/api/disruptions").json()
    assert stack2["count"] == 2
    stacked_ids = [d["affected_flight_id"] for d in stack2["disruptions"]]
    assert "6E-101" in stacked_ids
    assert "6E-103" in stacked_ids

    # Verify that the generated candidate plan mutates BOTH affected flights!
    plan = data2["selected_plan"]
    assert plan is not None
    plan_diff = plan.get("plan_diff", [])
    mutated_flight_ids = [op.get("flight_id") for op in plan_diff]
    assert "6E-101" in mutated_flight_ids
    assert "6E-103" in mutated_flight_ids

    # 3. Test Clearing the Incident Stack
    clear_res = client.post("/api/disruptions/clear")
    assert clear_res.status_code == 200
    stack_cleared = client.get("/api/disruptions").json()
    assert stack_cleared["count"] == 0


def test_hard_veto_cannot_be_approved():
    """Mandatory Safety Guardrail: Prohibits approving any plan with hard statutory or slot vetoes."""
    client = TestClient(app)

    # Trigger recovery with severe disruption that prompts an initial excessive delay
    res = client.post("/api/run_recovery", json={
        "duty_manager_message": "Extreme dense fog 6E-101 delay 400 mins"
    })
    assert res.status_code == 200
    data = res.json()
    run_id = data["run_id"]

    # Locate any vetoed plan in candidates
    vetoed_plan = next((c for c in data.get("candidates", []) if len(c.get("vetoed_by", [])) > 0), None)
    if vetoed_plan:
        bad_plan_id = vetoed_plan["plan_id"]
        # Attempt to approve the vetoed plan
        appr_res = client.post("/api/approve_plan", json={
            "run_id": run_id,
            "decision": "APPROVE",
            "selected_plan_id": bad_plan_id,
            "manager_notes": "Attempting illegal override"
        })
        assert appr_res.status_code == 400
        assert "MANDATORY SAFETY VIOLATION" in appr_res.json()["detail"]


def test_concurrent_recovery_requests():
    """Stress test: Concurrently runs 5 multi-agent recovery pipelines to verify thread safety."""
    client = TestClient(app)

    def trigger_run(flight_no: str):
        return client.post("/api/run_recovery", json={
            "duty_manager_message": f"Pre-flight inspection delay on {flight_no} at VOBL for 35m"
        })

    flights = ["6E-101", "6E-102", "6E-103", "6E-104", "6E-105"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(trigger_run, f) for f in flights]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("AWAITING_APPROVAL", "ESCALATED")
        assert "run_id" in data
