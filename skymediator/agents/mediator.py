"""
Mediator Agent — Multi-Objective Deliberation Orchestrator and Decision Arbiter.
Coordinates multi-agent rounds, filters hard vetoes, executes deterministic scoring,
reflects on operational trade-offs, and directs bounded transitions.
"""

from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan
from skymediator.tools.scoring import score_plan
from skymediator.tools.schedule import apply_plan_diff


class MediatorOutput(BaseModel):
    status: Literal["CONTINUE_DELIBERATION", "READY_FOR_APPROVAL", "ESCALATE"]
    top_candidate: Optional[Dict[str, Any]] = None
    ranked_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    reflection_notes: str
    escalation_reason: Optional[str] = None


class MediatorAgent:
    """Orchestrator and arbiter enforcing hard vetoes, deterministic scoring, and reflection."""

    def __init__(self, indifference_threshold: float = 0.05):
        self.indifference_threshold = indifference_threshold

    def adjudicate_round(
        self,
        round_number: int,
        max_rounds: int,
        candidates: List[Dict[str, Any]],
        base_schedule: List[Dict[str, Any]],
        passenger_reports: Optional[Dict[str, Any]] = None,
        cost_reports: Optional[Dict[str, Any]] = None,
        crew_decision: Optional[str] = None,
        slot_decision: Optional[str] = None,
        run_id: str = "DELIBERATE",
        disruption: Optional[Dict[str, Any]] = None
    ) -> MediatorOutput:
        """
        Adjudicates candidate plans in the current deliberation round.
        
        1. Checks for hard abstentions from compliance agents.
        2. Applies hard-filtering (candidates with vetoed_by != [] are rejected).
        3. Deterministically scores surviving candidates using multi-objective weights.
        4. Detects indifference margins (<= 0.05) triggering human escalation.
        5. Performs reflection pass analyzing operational trade-offs.
        6. Directs next state (CONTINUE_DELIBERATION, READY_FOR_APPROVAL, ESCALATE).
        """
        # Step 1: Check for Agent Abstention
        if crew_decision == "ABSTAIN":
            escalation_reason = (
                "Crew Legality agent abstained due to regulatory ambiguity or unindexed statutory clause. "
                "Immediate Duty Manager human intervention required."
            )
            logger.warning(f"[{run_id}] Mediator escalating due to Crew Legality ABSTENTION.")
            return MediatorOutput(
                status="ESCALATE",
                top_candidate=None,
                ranked_candidates=[],
                reflection_notes="Deliberation suspended: Statutory compliance ambiguity requires Duty Manager interpretation.",
                escalation_reason=escalation_reason
            )

        # Step 2: Hard Veto Filtering
        surviving: List[Dict[str, Any]] = []
        for cand in candidates:
            vetoed_by = cand.get("vetoed_by", [])
            if len(vetoed_by) == 0:
                surviving.append(cand)

        logger.info(
            f"[{run_id}] Round {round_number}: {len(surviving)} of {len(candidates)} "
            f"candidates survived hard vetoes."
        )

        # If no candidates survived in this round:
        if not surviving:
            if round_number < max_rounds:
                reflection = (
                    f"Round {round_number}: All proposed candidate plans were vetoed by statutory/slot authorities. "
                    f"Initiating counter-proposal deliberation loop for Round {round_number + 1}."
                )
                logger.info(f"[{run_id}] {reflection}")
                return MediatorOutput(
                    status="CONTINUE_DELIBERATION",
                    top_candidate=None,
                    ranked_candidates=[],
                    reflection_notes=reflection,
                    escalation_reason=None
                )
            else:
                escalation_reason = (
                    f"Deliberation exhausted: All candidate plans were vetoed across "
                    f"maximum permitted rounds ({max_rounds}). Escalated to Duty Manager for manual intervention."
                )
                logger.error(f"[{run_id}] {escalation_reason}")
                return MediatorOutput(
                    status="ESCALATE",
                    top_candidate=None,
                    ranked_candidates=[],
                    reflection_notes="Deliberation exhausted all bounded rounds without finding a legally compliant plan.",
                    escalation_reason=escalation_reason
                )

        # Step 3: Deterministic Multi-Objective Scoring
        ranked_list: List[Dict[str, Any]] = []
        for cand in surviving:
            plan_diff = cand.get("plan_diff", [])
            
            # Extract or calculate operational metrics
            delay_minutes = 0.0
            for op in plan_diff:
                if op.get("op") == "delay":
                    delay_minutes += float(op.get("delay_minutes", 0))

            # Retrieve passenger and cost metrics if available
            pax_rep = (passenger_reports or {}).get(cand.get("plan_id"), {})
            cost_rep = (cost_reports or {}).get(cand.get("plan_id"), {})

            missed_pax = pax_rep.get("total_affected_passengers", 0)
            total_cost = cost_rep.get("total_cost", delay_minutes * 150.0)

            # Pure deterministic scoring tool
            score_res = score_plan(
                delay_minutes=delay_minutes,
                missed_connections=missed_pax,
                total_cost=total_cost,
                crew_buffer_penalty=0.0
            )

            scored_cand = dict(cand)
            scored_cand["scores"] = score_res
            ranked_list.append(scored_cand)

        # Step 4: Rank candidates by composite penalty score (lower is better)
        ranked_list.sort(key=lambda x: x["scores"]["composite_score"])
        top_cand = ranked_list[0]

        # Step 5: Check Indifference Margin (Ambiguity trigger)
        if len(ranked_list) >= 2:
            s1 = ranked_list[0]["scores"]["composite_score"]
            s2 = ranked_list[1]["scores"]["composite_score"]
            diff = abs(s1 - s2)
            if diff <= self.indifference_threshold:
                escalation_reason = (
                    f"Margin of Indifference: Top candidate {ranked_list[0]['plan_id']} (Score: {s1:.3f}) "
                    f"and runner-up {ranked_list[1]['plan_id']} (Score: {s2:.3f}) differ by only {diff:.3f} "
                    f"(<= {self.indifference_threshold}). Escalated to Duty Manager to select preferred trade-off."
                )
                logger.info(f"[{run_id}] {escalation_reason}")
                return MediatorOutput(
                    status="ESCALATE",
                    top_candidate=top_cand,
                    ranked_candidates=ranked_list,
                    reflection_notes=(
                        f"Equally competitive recovery options identified with score difference of {diff:.3f}. "
                        f"Duty Manager discretion required between delay-minimizing vs cost-minimizing alternatives."
                    ),
                    escalation_reason=escalation_reason
                )

        # Step 6: Reflection Pass (Evaluating cross-agent trade-offs)
        cancellations = [op for op in top_cand.get("plan_diff", []) if op.get("op") == "cancel"]
        swaps = [op for op in top_cand.get("plan_diff", []) if op.get("op") == "swap_tail"]
        delays = [op for op in top_cand.get("plan_diff", []) if op.get("op") == "delay"]

        reflection_parts = [
            f"Evaluated {len(surviving)} surviving candidate plans in Round {round_number}.",
            f"Selected optimal candidate {top_cand.get('plan_id')} with composite penalty score {top_cand['scores']['composite_score']:.4f}."
        ]

        if swaps:
            reflection_parts.append(f"Employs {len(swaps)} tail swap(s) preserving schedule continuity without passenger delay.")
        if delays:
            max_d = max(d.get("delay_minutes", 0) for d in delays)
            reflection_parts.append(f"Incurs controlled departure delay of up to {max_d}m, strictly within legal crew FDP and slot limits.")
        if cancellations:
            reflection_parts.append(f"Includes {len(cancellations)} strategic flight cancellation(s) to protect systemic integrity.")

        reflection_notes = " ".join(reflection_parts)

        # Enhance reflection with Gemini LLM multi-objective trade-off analysis
        from skymediator.llm import reflect_mediator_tradeoffs, synthesize_occ_briefing
        llm_reflection = reflect_mediator_tradeoffs(ranked_list, round_number)
        if llm_reflection and not llm_reflection.startswith("[Deterministic"):
            reflection_notes = f"{reflection_notes} Trade-off Reflection: {llm_reflection}"

        # Synthesize Natural Language OCC Executive Briefing via Gemini
        briefing = synthesize_occ_briefing(
            plan=top_cand,
            scores=top_cand.get("scores", {}),
            disruption=disruption or {"hub": settings.HUB_AIRPORT, "round": round_number},
            hub=f"{settings.HUB_AIRPORT} ({settings.HUB_IATA})"
        )
        top_cand["occ_briefing"] = briefing

        output = MediatorOutput(
            status="READY_FOR_APPROVAL",
            top_candidate=top_cand,
            ranked_candidates=ranked_list,
            reflection_notes=reflection_notes,
            escalation_reason=None
        )

        span = TraceSpan(
            span_id=f"MED-{uuid4().hex[:6]}",
            run_id=run_id,
            round=round_number,
            agent="Mediator",
            action_type="ADJUDICATE",
            tool_name="score_plan",
            input_payload={"round": round_number, "surviving_count": len(surviving)},
            output_payload={
                "status": output.status,
                "top_plan_id": top_cand.get("plan_id"),
                "top_score": top_cand["scores"]["composite_score"]
            }
        )
        write_trace_span(span)

        return output
