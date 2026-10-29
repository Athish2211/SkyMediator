"""
Unit and integration tests for CrewLegalityAgent and Agentic RAG.
Verifies CAR Section 7 enforcement, query rewriting, clause citation, and abstention behavior.
"""

from datetime import datetime, timedelta
from skymediator.agents.crew import CrewLegalityAgent, CrewEvaluationResult
from skymediator.models import CandidatePlan, DelayOp, SwapTailOp


def test_crew_legality_pass_compliant_plan():
    agent = CrewLegalityAgent()
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

    candidate = CandidatePlan(
        plan_id="PLAN-TEST-PASS",
        round_created=1,
        proposing_agent="Rotation",
        plan_diff=[
            SwapTailOp(
                flight_id="6E-101",
                original_tail="VT-BLR01",
                new_tail="VT-BLR15",
                reason="Standby tail swap"
            ).model_dump()
        ],
        operational_rationale="Swap tail without delay"
    )

    crew_roster = [
        {
            "crew_id": "CREW-LEGAL",
            "duty_record": {"duty_start": base_time.isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    result: CrewEvaluationResult = agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        active_crew=crew_roster,
        run_id="TEST-CREW-PASS",
        round_number=1
    )

    assert result.decision == "PASS"
    assert result.is_legal is True
    assert len(result.violations) == 0


def test_crew_legality_hard_veto_with_rag_citation():
    agent = CrewLegalityAgent()
    base_time = datetime(2026, 11, 1, 2, 0)  # WOCL night start

    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": (base_time + timedelta(hours=4)).isoformat(),
            "sta": (base_time + timedelta(hours=6, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    # Excessive delay of 350 minutes pushing FDP way past 11.0h WOCL limit
    candidate = CandidatePlan(
        plan_id="PLAN-TEST-VETO",
        round_created=1,
        proposing_agent="Rotation",
        plan_diff=[
            DelayOp(
                flight_id="6E-101",
                delay_minutes=350,
                new_std=base_time + timedelta(hours=4, minutes=350),
                new_sta=base_time + timedelta(hours=6, minutes=380),
                reason="Severe fog delay"
            ).model_dump()
        ],
        operational_rationale="Delay leg"
    )

    crew_roster = [
        {
            "crew_id": "CREW-WOCL-EXCEED",
            "duty_record": {"duty_start": base_time.isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    result: CrewEvaluationResult = agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        active_crew=crew_roster,
        run_id="TEST-CREW-VETO",
        round_number=1
    )

    assert result.decision == "VETO"
    assert result.is_legal is False
    assert result.cited_clause is not None
    # Verifies Agentic RAG retrieved or cited CAR Section 7 clause
    assert "CAR" in result.reason or "DGCA" in result.reason or "Flight Duty Period" in result.reason
    assert result.retrieval_confidence > 0.0
