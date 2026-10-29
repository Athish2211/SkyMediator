"""
LangGraph Multi-Agent Orchestration — 7-Agent Deliberation Suite.
Orchestrates Sentinel, Rotation, Crew Legality (with Agentic RAG), Slot,
Passenger, Cost, and Mediator agents within a bounded, deterministic state graph.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from langgraph.graph import StateGraph, END

from skymediator.config import settings
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import PlanState, CandidatePlan
from skymediator.agents.sentinel import SentinelAgent
from skymediator.agents.rotation import RotationAgent
from skymediator.agents.crew import CrewLegalityAgent
from skymediator.agents.slot import SlotAgent
from skymediator.agents.passenger import PassengerAgent
from skymediator.agents.cost import CostAgent
from skymediator.agents.mediator import MediatorAgent


def node_initialize_disruption(state: PlanState) -> Dict[str, Any]:
    """Initializes the orchestrator run, parses Duty Manager natural language message if present, and sets round = 1."""
    run_id = state.get("run_id") or f"REC-{uuid4().hex[:6].upper()}"
    logger.info(f"[{run_id}] Initializing disruption recovery run.")

    dm_message = state.get("duty_manager_message") or state.get("disruption", {}).get("message")
    parsed_disruption = None
    disruption = dict(state.get("disruption") or {})

    if dm_message:
        from skymediator.llm import parse_duty_manager_disruption
        base_schedule = state.get("base_schedule", [])
        parsed_disruption = parse_duty_manager_disruption(dm_message, base_schedule=base_schedule)

        # Merge parsed values without overriding explicitly provided non-empty fields
        for k, v in parsed_disruption.items():
            if k not in disruption or disruption[k] is None:
                disruption[k] = v

        disruption["raw_message"] = dm_message
        logger.info(f"[{run_id}] Mediator LLM understood Duty Manager message: {parsed_disruption.get('tactical_summary')}")

        parse_span = TraceSpan(
            span_id=f"PARSE-{uuid4().hex[:6]}",
            run_id=run_id,
            round=1,
            agent="Mediator",
            action_type="PARSE_DUTY_MANAGER_MESSAGE",
            input_payload={"message": dm_message},
            output_payload=parsed_disruption
        )
        write_trace_span(parse_span)

    span = TraceSpan(
        span_id=f"INIT-{uuid4().hex[:6]}",
        run_id=run_id,
        round=1,
        agent="Mediator",
        action_type="INITIALIZE_DISRUPTION",
        input_payload={"disruption": disruption, "duty_manager_message": dm_message},
        output_payload={"status": "INITIALIZED", "parsed_disruption": parsed_disruption}
    )
    write_trace_span(span)

    return {
        "run_id": run_id,
        "version": 1,
        "round": 1,
        "max_rounds": state.get("max_rounds") or settings.MAX_NEGOTIATION_ROUNDS,
        "status": "INITIALIZED",
        "duty_manager_message": dm_message,
        "parsed_disruption": parsed_disruption,
        "disruption": disruption,
        "constraints_log": list(state.get("constraints_log") or []),
        "candidates": list(state.get("candidates") or []),
        "surviving_candidates": [],
        "selected_plan": None,
        "escalation_reason": None,
        "passenger_reports": {},
        "cost_reports": {}
    }


def node_sentinel_forecast(state: PlanState) -> Dict[str, Any]:
    """
    Sentinel Agent evaluates weather observations or AOG signals to establish
    disruption probability, expected start/end times, and recommended tactical actions.
    """
    run_id = state["run_id"]
    disruption = state.get("disruption", {})
    airport = disruption.get("airport", settings.HUB_AIRPORT)

    # Use supplied observation or synthesize from disruption parameters
    current_obs = disruption.get("current_observation")
    if not current_obs:
        is_severe = disruption.get("severity") == "SEVERE"
        vis = 350 if is_severe else (750 if disruption.get("type") == "fog" else 4000)
        rvr = 300 if is_severe else (650 if disruption.get("type") == "fog" else 2000)
        current_obs = {
            "station": airport,
            "ts": disruption.get("start_time", datetime.utcnow().isoformat()),
            "visibility_m": disruption.get("visibility_m", vis),
            "rvr_m": disruption.get("rvr_m", rvr),
            "temp_c": 16.0,
            "dewpoint_c": 15.5,
            "dewpoint_depression": 0.5,
            "wind_speed_kts": 3.0,
            "wind_dir_deg": 90,
            "cloud_ceiling_ft": 200,
            "is_morning_window": 1,
            "present_weather": ["FG"]
        }

    sentinel = SentinelAgent(airport=airport)
    forecast = sentinel.evaluate_forecast(current_obs, run_id=run_id)

    return {
        "sentinel_forecast": forecast.model_dump()
    }


def node_propose_recovery(state: PlanState) -> Dict[str, Any]:
    """
    Rotation Agent proposes a candidate PlanDiff.
    In Round 1, proposes an initial operational fix.
    In Round 2+, inspects constraints_log to synthesize a legal counter-proposal.
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    disruption = state.get("disruption", {})
    base_schedule = state.get("base_schedule", [])
    constraints_log = state.get("constraints_log", [])

    logger.info(f"[{run_id}] Round {curr_round}: Rotation formulating candidate recovery plan.")

    rotation_agent = RotationAgent()
    candidate = rotation_agent.propose_candidate_plan(
        round_number=curr_round,
        disruption=disruption,
        base_schedule=base_schedule,
        constraints_log=constraints_log,
        run_id=run_id
    )

    cand_dict = candidate.model_dump()
    cand_dict.setdefault("agent_perspectives", {})["rotation"] = candidate.operational_rationale
    candidates = list(state.get("candidates", []))
    candidates.append(cand_dict)

    return {
        "candidates": candidates,
        "status": "DELIBERATING"
    }


def node_check_crew_legality(state: PlanState) -> Dict[str, Any]:
    """
    Crew Legality Agent verifies FDTL compliance using deterministic calc_duty_time and Agentic RAG.
    Holds absolute HARD VETO authority.
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    candidates = list(state.get("candidates", []))
    constraints_log = list(state.get("constraints_log", []))

    if not candidates:
        return state

    latest_dict = candidates[-1]
    candidate = CandidatePlan.model_validate(latest_dict)
    base_schedule = state.get("base_schedule", [])
    active_crew = state.get("active_crew", [])

    crew_agent = CrewLegalityAgent()
    res = crew_agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        active_crew=active_crew,
        run_id=run_id,
        round_number=curr_round
    )

    crew_decision = res.decision

    if res.decision == "VETO":
        logger.warning(f"[{run_id}] Crew Legality issued HARD VETO: {res.reason}")
        if "crew" not in latest_dict.setdefault("vetoed_by", []):
            latest_dict["vetoed_by"].append("crew")
        latest_dict.setdefault("veto_reasons", {})["crew"] = res.reason
        latest_dict.setdefault("agent_perspectives", {})["crew"] = res.reason

        constraints_log.append({
            "round": curr_round,
            "agent": "CrewLegality",
            "constraint_type": "FDTL",
            "clause_id": res.cited_clause,
            "reason": res.reason,
            "target_flight_id": res.violations[0].get("flight_id") if res.violations else None
        })

    elif res.decision == "ABSTAIN":
        logger.warning(f"[{run_id}] Crew Legality ABSTAINED: {res.reason}")
        latest_dict.setdefault("agent_perspectives", {})["crew"] = f"ABSTAIN: {res.reason}"

    else:
        from skymediator.llm import explain_crew_legality_reasoning
        crew_id = active_crew[0].get("crew_id", "CREW-CAPT-01") if active_crew else "CREW-CAPT-01"
        comp_msg = explain_crew_legality_reasoning(
            crew_id=crew_id,
            is_legal=True,
            violation=None,
            cited_clause="DGCA CAR Section 7, Series J, Part III"
        )
        latest_dict.setdefault("compliance_notes", {})["crew"] = comp_msg
        latest_dict.setdefault("agent_perspectives", {})["crew"] = comp_msg

    return {
        "candidates": candidates,
        "constraints_log": constraints_log,
        "crew_decision": crew_decision
    }


def node_check_slot_constraints(state: PlanState) -> Dict[str, Any]:
    """
    Slot Agent validates movement capacity and night curfews using check_slot.
    Holds absolute HARD VETO authority.
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    candidates = list(state.get("candidates", []))
    constraints_log = list(state.get("constraints_log", []))

    if not candidates:
        return state

    latest_dict = candidates[-1]
    candidate = CandidatePlan.model_validate(latest_dict)
    base_schedule = state.get("base_schedule", [])
    slot_windows = state.get("slot_windows", [])

    slot_agent = SlotAgent(hub_airport=settings.HUB_AIRPORT)
    res = slot_agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        slot_windows=slot_windows,
        run_id=run_id,
        round_number=curr_round
    )

    slot_decision = res.decision

    if res.decision == "VETO":
        logger.warning(f"[{run_id}] Slot Agent issued HARD VETO: {res.reason}")
        if "slot" not in latest_dict.setdefault("vetoed_by", []):
            latest_dict["vetoed_by"].append("slot")
        latest_dict.setdefault("veto_reasons", {})["slot"] = res.reason
        latest_dict.setdefault("agent_perspectives", {})["slot"] = res.reason

        constraints_log.append({
            "round": curr_round,
            "agent": "SlotAgent",
            "constraint_type": "SLOT",
            "reason": res.reason,
            "target_flight_id": res.violated_windows[0].get("affected_flights", [None])[0] if res.violated_windows else None
        })
    else:
        slot_msg = res.reason
        latest_dict.setdefault("compliance_notes", {})["slot"] = slot_msg
        latest_dict.setdefault("agent_perspectives", {})["slot"] = slot_msg

    return {
        "candidates": candidates,
        "constraints_log": constraints_log,
        "slot_decision": slot_decision
    }


def node_evaluate_passenger_impact(state: PlanState) -> Dict[str, Any]:
    """
    Passenger Agent calculates broken connections and itinerary delays for latest candidate.
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    candidates = list(state.get("candidates", []))
    passenger_reports = dict(state.get("passenger_reports") or {})

    if not candidates:
        return state

    latest_dict = candidates[-1]
    candidate = CandidatePlan.model_validate(latest_dict)
    base_schedule = state.get("base_schedule", [])

    pax_agent = PassengerAgent()
    pax_res = pax_agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        run_id=run_id,
        round_number=curr_round
    )

    passenger_reports[candidate.plan_id] = pax_res.model_dump()

    # Use LLM synthesis for Passenger agent perspective when available
    pax_pers = f"Passenger Care: {pax_res.total_affected_passengers} passengers disrupted, {pax_res.missed_connections_count} broken connections. Care facilities arranged under DGCA CAR Sec 3."
    from skymediator.llm import synthesize_passenger_cost_rationale, is_gemini_available
    if is_gemini_available():
        llm_pax = synthesize_passenger_cost_rationale(
            plan_id=candidate.plan_id,
            missed_connections=pax_res.missed_connections_count,
            total_cost=0.0,
            affected_pax=pax_res.total_affected_passengers
        )
        if llm_pax and not llm_pax.startswith("[Deterministic"):
            pax_pers = llm_pax
    latest_dict.setdefault("agent_perspectives", {})["passenger"] = pax_pers

    return {
        "candidates": candidates,
        "passenger_reports": passenger_reports
    }


def node_evaluate_cost_impact(state: PlanState) -> Dict[str, Any]:
    """
    Cost Agent estimates financial liabilities (delays, cancellations, DGCA care facilities).
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    candidates = list(state.get("candidates", []))
    passenger_reports = dict(state.get("passenger_reports") or {})
    cost_reports = dict(state.get("cost_reports") or {})

    if not candidates:
        return state

    latest_dict = candidates[-1]
    candidate = CandidatePlan.model_validate(latest_dict)
    base_schedule = state.get("base_schedule", [])

    pax_rep = passenger_reports.get(candidate.plan_id, {})
    missed_pax = pax_rep.get("total_affected_passengers", 0)

    cost_agent = CostAgent()
    cost_res = cost_agent.evaluate_candidate_plan(
        candidate=candidate,
        base_schedule=base_schedule,
        missed_connections=missed_pax,
        run_id=run_id,
        round_number=curr_round
    )

    cost_reports[candidate.plan_id] = cost_res.model_dump()

    # Use LLM synthesis for Cost agent perspective when available
    from skymediator.llm import synthesize_passenger_cost_rationale, is_gemini_available
    missed_conn = pax_rep.get("missed_connections_count", 0)
    affected_pax = pax_rep.get("total_affected_passengers", 0)
    cost_pers = f"Financial Exposure: INR {cost_res.total_cost:,.0f} (Delay costs: INR {cost_res.delay_cost:,.0f}, DGCA statutory care: INR {cost_res.statutory_compensation_cost:,.0f})."
    if is_gemini_available():
        llm_cost = synthesize_passenger_cost_rationale(
            plan_id=candidate.plan_id,
            missed_connections=missed_conn,
            total_cost=cost_res.total_cost,
            affected_pax=affected_pax
        )
        if llm_cost and not llm_cost.startswith("[Deterministic"):
            cost_pers = llm_cost
    latest_dict.setdefault("agent_perspectives", {})["cost"] = cost_pers

    return {
        "candidates": candidates,
        "cost_reports": cost_reports
    }


def node_mediator_adjudicate(state: PlanState) -> Dict[str, Any]:
    """
    Mediator Agent:
    1. Checks compliance agent abstentions.
    2. Enforces hard veto filtering.
    3. Deterministically scores surviving candidate plans.
    4. Evaluates indifference margins and reflects on systemic trade-offs.
    5. Directs next deliberation round or human duty manager escalation.
    """
    run_id = state["run_id"]
    curr_round = state.get("round", 1)
    max_rounds = state.get("max_rounds", settings.MAX_NEGOTIATION_ROUNDS)
    candidates = list(state.get("candidates", []))
    base_schedule = state.get("base_schedule", [])
    passenger_reports = state.get("passenger_reports")
    cost_reports = state.get("cost_reports")
    crew_decision = state.get("crew_decision")
    slot_decision = state.get("slot_decision")

    mediator = MediatorAgent()
    decision = mediator.adjudicate_round(
        round_number=curr_round,
        max_rounds=max_rounds,
        candidates=candidates,
        base_schedule=base_schedule,
        passenger_reports=passenger_reports,
        cost_reports=cost_reports,
        crew_decision=crew_decision,
        slot_decision=slot_decision,
        run_id=run_id
    )

    # Persist snapshot of all candidates into plan_revisions table
    try:
        from skymediator.events import record_plan_revision
        for c in candidates:
            record_plan_revision(c, run_id=run_id, round_number=c.get("round_created", curr_round))
    except Exception as e:
        logger.debug(f"Plan revision persistence notice: {e}")

    if decision.status == "READY_FOR_APPROVAL":
        # Ensure is_feasible is explicitly set on dictionary for serialized consumers
        top_cand = decision.top_candidate
        if top_cand:
            top_cand["is_feasible"] = len(top_cand.get("vetoed_by", [])) == 0

        # Record pending recommendation in persistent decision audit table
        try:
            from skymediator.events import record_decision
            record_decision({
                "decision_id": f"DEC-{run_id}-R{curr_round}",
                "run_id": run_id,
                "disruption_id": state.get("disruption", {}).get("scenario_id") or "DISPATCH",
                "plan_id": top_cand.get("plan_id") if top_cand else None,
                "round_number": curr_round,
                "duty_manager_action": "PENDING",
                "duty_manager_id": "System (Mediator)",
                "duty_manager_notes": "Awaiting Human Duty Manager Review and Authorization",
                "proposed_diff": top_cand.get("plan_diff", []) if top_cand else [],
                "validation_outcomes": {
                    "compliance_notes": top_cand.get("compliance_notes", {}),
                    "veto_reasons": top_cand.get("veto_reasons", {}),
                    "agent_perspectives": top_cand.get("agent_perspectives", {})
                } if top_cand else {},
                "vetoed_by": top_cand.get("vetoed_by", []) if top_cand else [],
                "is_feasible_at_decision": bool(top_cand and len(top_cand.get("vetoed_by", [])) == 0),
                "mediator_rationale": decision.reflection_notes,
                "final_status": "RECOMMENDED"
            })
        except Exception as e:
            logger.debug(f"Decision persistence notice: {e}")

        return {
            "status": "AWAITING_APPROVAL",
            "selected_plan": top_cand,
            "surviving_candidates": decision.ranked_candidates,
            "reflection_notes": decision.reflection_notes,
            "escalation_reason": None
        }

    elif decision.status == "CONTINUE_DELIBERATION":
        return {
            "status": "DELIBERATING",
            "round": curr_round + 1,
            "reflection_notes": decision.reflection_notes
        }

    else:  # ESCALATE
        return {
            "status": "ESCALATED",
            "selected_plan": None,
            "escalation_reason": decision.escalation_reason,
            "reflection_notes": decision.reflection_notes
        }


def router_mediator_decision(state: PlanState) -> Literal["propose_recovery", "__end__"]:
    """Conditional router: loops back for counter-proposals or exits to approval/escalation."""
    if state.get("status") == "DELIBERATING":
        return "propose_recovery"
    return "__end__"


def build_recovery_graph() -> StateGraph:
    """Builds and compiles the complete 7-agent StateGraph."""
    builder = StateGraph(PlanState)

    # Register Nodes
    builder.add_node("initialize_disruption", node_initialize_disruption)
    builder.add_node("predict_disruption", node_sentinel_forecast)
    builder.add_node("propose_recovery", node_propose_recovery)
    builder.add_node("check_crew_legality", node_check_crew_legality)
    builder.add_node("check_slot_constraints", node_check_slot_constraints)
    builder.add_node("evaluate_passenger_impact", node_evaluate_passenger_impact)
    builder.add_node("evaluate_cost_impact", node_evaluate_cost_impact)
    builder.add_node("mediator_adjudicate", node_mediator_adjudicate)

    # Wire Edges
    builder.set_entry_point("initialize_disruption")
    builder.add_edge("initialize_disruption", "predict_disruption")
    builder.add_edge("predict_disruption", "propose_recovery")
    builder.add_edge("propose_recovery", "check_crew_legality")
    builder.add_edge("check_crew_legality", "check_slot_constraints")
    builder.add_edge("check_slot_constraints", "evaluate_passenger_impact")
    builder.add_edge("evaluate_passenger_impact", "evaluate_cost_impact")
    builder.add_edge("evaluate_cost_impact", "mediator_adjudicate")

    # Conditional Deliberation Loop
    builder.add_conditional_edges(
        "mediator_adjudicate",
        router_mediator_decision,
        {
            "propose_recovery": "propose_recovery",
            "__end__": END
        }
    )

    return builder.compile()


def execute_replan_round(state: Dict[str, Any], human_feedback: str) -> Dict[str, Any]:
    """
    PROP-04: Human Replan Feedback Loop.
    Executes an additional deliberation round incorporating Duty Manager human feedback as a constraint.
    Synthesizes a new candidate plan via Rotation, verifies with Crew Legality, Slot Capacity,
    Passenger Impact, and Cost agents, and adjudicates the revised plan via Mediator.
    """
    curr_round = state.get("round", 1)
    next_round = curr_round + 1
    state["round"] = next_round

    constraints_log = list(state.get("constraints_log") or [])
    constraints_log.append({
        "round": next_round,
        "agent": "DutyManager",
        "constraint_type": "HUMAN_REVISION",
        "reason": human_feedback,
        "target_flight_id": state.get("disruption", {}).get("affected_flight_id", "6E-101")
    })
    state["constraints_log"] = constraints_log

    # 1. Propose candidate
    up1 = node_propose_recovery(state)
    state.update(up1)

    # 2. Check crew legality
    up2 = node_check_crew_legality(state)
    state.update(up2)

    # 3. Check slot constraints
    up3 = node_check_slot_constraints(state)
    state.update(up3)

    # 4. Evaluate passenger impact
    up4 = node_evaluate_passenger_impact(state)
    state.update(up4)

    # 5. Evaluate cost impact
    up5 = node_evaluate_cost_impact(state)
    state.update(up5)

    # 6. Mediator adjudicate
    up6 = node_mediator_adjudicate(state)
    state.update(up6)

    # Ensure the newly synthesized replan candidate is selected if feasible
    if state.get("candidates"):
        new_candidate = state["candidates"][-1]
        if len(new_candidate.get("vetoed_by", [])) == 0:
            new_candidate["is_feasible"] = True
            state["selected_plan"] = new_candidate
            state["status"] = "AWAITING_APPROVAL"

    return state

