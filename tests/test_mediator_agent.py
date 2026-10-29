"""
Unit tests for MediatorAgent.
Verifies hard veto filtering, multi-objective scoring, reflection, indifference escalation, and bounded round handling.
"""

from skymediator.agents.mediator import MediatorAgent, MediatorOutput


def test_mediator_hard_veto_filtering():
    mediator = MediatorAgent()
    
    candidates = [
        {
            "plan_id": "PLAN-VETOED-01",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "delay", "delay_minutes": 180}],
            "vetoed_by": ["crew"],
            "veto_reasons": {"crew": "Exceeds FDP"}
        },
        {
            "plan_id": "PLAN-VETOED-02",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "swap_tail", "flight_id": "6E-101", "original_tail": "VT-BLR01", "new_tail": "VT-BLR15"}],
            "vetoed_by": ["slot"],
            "veto_reasons": {"slot": "Slot capacity overflow"}
        }
    ]

    # In round 1, if all plans vetoed -> CONTINUE_DELIBERATION for next round
    res: MediatorOutput = mediator.adjudicate_round(
        round_number=1,
        max_rounds=3,
        candidates=candidates,
        base_schedule=[]
    )

    assert res.status == "CONTINUE_DELIBERATION"
    assert res.top_candidate is None

    # In round 3, if all plans vetoed -> ESCALATE
    res3: MediatorOutput = mediator.adjudicate_round(
        round_number=3,
        max_rounds=3,
        candidates=candidates,
        base_schedule=[]
    )

    assert res3.status == "ESCALATE"
    assert "All candidate plans were vetoed" in res3.escalation_reason


def test_mediator_selects_best_surviving_candidate():
    mediator = MediatorAgent()

    candidates = [
        {
            "plan_id": "PLAN-A",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 120}],
            "vetoed_by": []
        },
        {
            "plan_id": "PLAN-B",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 25}],
            "vetoed_by": []
        }
    ]

    res: MediatorOutput = mediator.adjudicate_round(
        round_number=1,
        max_rounds=3,
        candidates=candidates,
        base_schedule=[]
    )

    # PLAN-B has smaller delay (25m vs 120m) -> lower penalty score -> selected!
    assert res.status == "READY_FOR_APPROVAL"
    assert res.top_candidate is not None
    assert res.top_candidate["plan_id"] == "PLAN-B"
    assert len(res.reflection_notes) > 0


def test_mediator_indifference_margin_escalation():
    # Set indifference threshold = 0.05
    mediator = MediatorAgent(indifference_threshold=0.05)

    # Two nearly identical plans (e.g. 30m vs 31m delay)
    candidates = [
        {
            "plan_id": "PLAN-01",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 30}],
            "vetoed_by": []
        },
        {
            "plan_id": "PLAN-02",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "delay", "flight_id": "6E-101", "delay_minutes": 31}],
            "vetoed_by": []
        }
    ]

    res: MediatorOutput = mediator.adjudicate_round(
        round_number=1,
        max_rounds=3,
        candidates=candidates,
        base_schedule=[]
    )

    # Since score difference is <= 0.05, it must escalate to Duty Manager
    assert res.status == "ESCALATE"
    assert "Margin of Indifference" in res.escalation_reason
    assert res.top_candidate is not None


def test_mediator_abstention_escalation():
    mediator = MediatorAgent()

    candidates = [
        {
            "plan_id": "PLAN-VALID",
            "round_created": 1,
            "proposing_agent": "Rotation",
            "plan_diff": [{"op": "swap_tail", "flight_id": "6E-101", "original_tail": "VT-BLR01", "new_tail": "VT-BLR15"}],
            "vetoed_by": []
        }
    ]

    # Crew Legality emitted ABSTAIN due to regulatory ambiguity
    res: MediatorOutput = mediator.adjudicate_round(
        round_number=1,
        max_rounds=3,
        candidates=candidates,
        base_schedule=[],
        crew_decision="ABSTAIN"
    )

    assert res.status == "ESCALATE"
    assert "abstained" in res.escalation_reason.lower()
