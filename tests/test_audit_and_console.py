"""
Automated E2E and Unit Tests for:
- Feature A: Agent Operations Console & SSE Streaming
- Feature B: Persistent Decision Audit Trail & Regulatory Safeguards
- Feature C: Premium OCC Multi-View Web Architecture
"""

import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from skymediator.app.server import app
from skymediator.config import settings
from skymediator.db import get_connection, init_db
from skymediator.events import AgentEvent, broker, record_decision, record_plan_revision
from skymediator.fixtures import seed_database
from skymediator.ingest.make_scenarios import seed_scenarios

# Ensure database is fresh and seeded
init_db(settings.DB_PATH)
seed_database(settings.DB_PATH)
seed_scenarios(settings.DB_PATH)

client = TestClient(app)


def test_schema_persistence_tables_exist():
    """Verifies agent_events, plan_revisions, and decision_records tables exist in SQLite."""
    conn = get_connection(settings.DB_PATH)
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "agent_events" in tables
        assert "plan_revisions" in tables
        assert "decision_records" in tables
    finally:
        conn.close()


def test_console_and_audit_routes_render_html():
    """Verifies that /, /console, /agent-console, /audit, and /decision-history render successfully."""
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "Agent Operations Console" in r_dash.text
    assert "Decision Audit Trail" in r_dash.text

    r_con = client.get("/console")
    assert r_con.status_code == 200
    assert "Agent Operations Console" in r_con.text
    assert "text/html" in r_con.headers["content-type"]

    r_con_alias = client.get("/agent-console")
    assert r_con_alias.status_code == 200

    r_aud = client.get("/audit")
    assert r_aud.status_code == 200
    assert "Decision Audit Trail" in r_aud.text
    assert "text/html" in r_aud.headers["content-type"]

    r_aud_alias = client.get("/decision-history")
    assert r_aud_alias.status_code == 200


def test_event_broker_publish_and_query():
    """Verifies AgentEvent publishing, SQLite persistence, and filtering API."""
    run_id = f"TEST-RUN-{uuid4().hex[:6].upper()}"
    evt = AgentEvent(
        run_id=run_id,
        round_number=1,
        event_type="proposal_created",
        actor="Rotation",
        recipient="CrewLegality",
        status="SUCCESS",
        summary="Test schedule mutation swap tail",
        structured_payload={"test_key": "test_val"}
    )
    broker.publish(evt, persist=True)

    # Query via API
    res = client.get(f"/api/events?run_id={run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    found = next((e for e in data["events"] if e["event_id"] == evt.event_id), None)
    assert found is not None
    assert found["actor"] == "Rotation"
    assert found["recipient"] == "CrewLegality"
    assert found["event_type"] == "proposal_created"
    assert found["structured_payload"]["test_key"] == "test_val"


def test_recovery_run_emits_events_and_plan_revisions():
    """Verifies that running recovery automatically persists events and plan revisions."""
    trigger_res = client.post(
        "/api/run_recovery",
        json={"scenario_id": "SCENARIO_02_SEVERE_CAT3_FOG"}
    )
    assert trigger_res.status_code == 200
    res_data = trigger_res.json()
    run_id = res_data["run_id"]

    # Check that events were persisted for this run
    evts_res = client.get(f"/api/events?run_id={run_id}")
    assert evts_res.status_code == 200
    evts = evts_res.json()["events"]
    assert len(evts) >= 3

    actors = [e["actor"] for e in evts]
    assert "Mediator" in actors
    assert "Rotation" in actors

    # Check plan revisions in database
    revs_res = client.get(f"/api/audit/revisions?run_id={run_id}")
    assert revs_res.status_code == 200
    revs = revs_res.json()["revisions"]
    assert len(revs) >= 1
    assert revs[0]["run_id"] == run_id


def test_mandatory_safety_guardrail_blocks_illegal_plan_approval():
    """
    STRICT SAFETY TEST:
    A duty manager CANNOT approve a candidate plan with a non-empty vetoed_by list or marked infeasible.
    """
    illegal_run_id = f"ILLEGAL-RUN-{uuid4().hex[:6].upper()}"
    illegal_plan_id = "PLAN-ILLEGAL-FDTL"

    # Seed an illegal vetoed plan revision into the database
    record_plan_revision(
        candidate={
            "plan_id": illegal_plan_id,
            "proposing_agent": "Rotation",
            "operational_rationale": "Illegal excessive delay violating pilot FDTL",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 360, "new_std": "2026-11-01T12:00:00", "new_sta": "2026-11-01T14:30:00", "reason": "Weather delay"}],
            "vetoed_by": ["crew"],
            "veto_reasons": {"crew": "Exceeds 11.0h WOCL statutory maximum FDP"},
            "is_feasible": False,
            "scores": {"composite_score": 0.85}
        },
        run_id=illegal_run_id,
        round_number=1
    )

    # Attempt to approve this illegal plan
    bad_approve_res = client.post(
        "/api/approve_plan",
        json={
            "run_id": illegal_run_id,
            "decision": "APPROVE",
            "selected_plan_id": illegal_plan_id,
            "manager_notes": "Attempting unauthorized approval of illegal plan"
        }
    )
    # Must be strictly rejected with HTTP 400 Bad Request
    assert bad_approve_res.status_code == 400
    detail = bad_approve_res.json()["detail"]
    assert "MANDATORY SAFETY VIOLATION" in detail
    assert "crew" in detail


def test_duty_manager_decision_persistence_and_audit_export():
    """Verifies that valid approvals/rejections are recorded in SQLite and exportable."""
    run_id = f"AUDIT-RUN-{uuid4().hex[:6].upper()}"
    plan_id = "PLAN-COMPLIANT-R1"

    # Seed compliant plan revision
    record_plan_revision(
        candidate={
            "plan_id": plan_id,
            "proposing_agent": "Rotation",
            "operational_rationale": "Compliant tail swap to standby tail VT-BLR15",
            "plan_diff": [{"op": "swap_tail", "flight_id": "6E-101", "original_tail": "VT-BLR01", "new_tail": "VT-BLR15", "reason": "Swap to standby"}],
            "vetoed_by": [],
            "veto_reasons": {},
            "is_feasible": True,
            "scores": {"composite_score": 0.012}
        },
        run_id=run_id,
        round_number=1
    )

    # 1. Submit approval
    appr_res = client.post(
        "/api/approve_plan",
        json={
            "run_id": run_id,
            "decision": "APPROVE",
            "selected_plan_id": plan_id,
            "manager_notes": "Formally authorized by Duty Manager Athish Raj."
        }
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "APPROVED"

    # 2. Verify persistence in decision_records table
    conn = get_connection(settings.DB_PATH)
    try:
        row = conn.execute(
            "SELECT * FROM decision_records WHERE run_id = ? AND duty_manager_action = 'APPROVED'",
            (run_id,)
        ).fetchone()
        assert row is not None
        assert row["plan_id"] == plan_id
        assert row["duty_manager_id"] == "Athish Raj (Duty Manager)"
        assert "Formally authorized" in row["duty_manager_notes"]
        assert row["is_feasible_at_decision"] == 1
    finally:
        conn.close()

    # 3. Verify via Audit API
    audit_res = client.get(f"/api/audit/decisions?run_id={run_id}")
    assert audit_res.status_code == 200
    decisions = audit_res.json()["decisions"]
    assert len(decisions) >= 1
    assert decisions[0]["duty_manager_action"] == "APPROVED"

    # 4. Verify CSV Export
    csv_res = client.get(f"/api/audit/export?format=csv&run_id={run_id}")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert run_id in csv_res.text
    assert "APPROVED" in csv_res.text

    # 5. Verify JSON Export
    json_res = client.get(f"/api/audit/export?format=json&run_id={run_id}")
    assert json_res.status_code == 200
    assert json_res.json()["count"] >= 1


def test_revision_side_by_side_comparison():
    """Verifies /api/audit/revisions/compare computes structured differences between two plans."""
    cmp_run_id = f"CMP-RUN-{uuid4().hex[:6].upper()}"

    record_plan_revision(
        candidate={
            "plan_id": "PLAN-R1-VETOED",
            "proposing_agent": "Rotation",
            "operational_rationale": "Excessive delay proposal",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 300, "new_std": "2026-11-01T11:00:00", "new_sta": "2026-11-01T13:30:00", "reason": "Holding delay"}],
            "vetoed_by": ["crew"],
            "is_feasible": False,
            "scores": {"composite_score": 0.88}
        },
        run_id=cmp_run_id,
        round_number=1
    )

    record_plan_revision(
        candidate={
            "plan_id": "PLAN-R2-RESOLVED",
            "proposing_agent": "Rotation",
            "operational_rationale": "Calibrated delay counter-proposal",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 25, "new_std": "2026-11-01T06:25:00", "new_sta": "2026-11-01T08:55:00", "reason": "Legal counter"}],
            "vetoed_by": [],
            "is_feasible": True,
            "scores": {"composite_score": 0.019}
        },
        run_id=cmp_run_id,
        round_number=2
    )

    cmp_res = client.get(
        f"/api/audit/revisions/compare?run_id={cmp_run_id}&plan_a=PLAN-R1-VETOED&plan_b=PLAN-R2-RESOLVED"
    )
    assert cmp_res.status_code == 200
    data = cmp_res.json()
    assert data["feasibility_comparison"]["PLAN-R1-VETOED_feasible"] is False
    assert data["feasibility_comparison"]["PLAN-R2-RESOLVED_feasible"] is True
    assert data["feasibility_comparison"]["PLAN-R1-VETOED_vetoed_by"] == ["crew"]
    assert data["feasibility_comparison"]["PLAN-R2-RESOLVED_vetoed_by"] == []


def test_rejection_and_replan_recording():
    """Verifies that duty manager rejection and replan requests are properly recorded."""
    run_id = f"REPLAN-RUN-{uuid4().hex[:6].upper()}"
    plan_id = "PLAN-R1-DISPATCH"

    record_plan_revision(
        candidate={
            "plan_id": plan_id,
            "proposing_agent": "Rotation",
            "operational_rationale": "Initial dispatch",
            "plan_diff": [{"op": "cancel", "flight_id": "6E-101", "reason": "Weather cancellation"}],
            "vetoed_by": [],
            "is_feasible": True
        },
        run_id=run_id,
        round_number=1
    )

    # Duty Manager requests replan
    replan_res = client.post(
        "/api/approve_plan",
        json={
            "run_id": run_id,
            "decision": "REPLAN",
            "selected_plan_id": plan_id,
            "manager_notes": "Avoid flight cancellation; evaluate tail swap to VT-BLR15."
        }
    )
    assert replan_res.status_code == 200
    assert replan_res.json()["status"] == "REVISION_REQUESTED"

    # Check audit record
    audit_res = client.get(f"/api/audit/decisions?run_id={run_id}&action=REVISION_REQUESTED")
    assert audit_res.status_code == 200
    assert audit_res.json()["total"] >= 1
    assert "Avoid flight cancellation" in audit_res.json()["decisions"][0]["duty_manager_notes"]

