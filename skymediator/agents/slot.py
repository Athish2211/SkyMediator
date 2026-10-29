"""
Slot Agent — Airport Slot Capacity and Night Curfew Enforcement.
Validates arrival and departure movement density against airport capacity.
Holds absolute HARD VETO authority.
"""

from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan
from skymediator.tools.slots import check_slot
from skymediator.tools.schedule import apply_plan_diff


class SlotEvaluationResult(BaseModel):
    decision: Literal["PASS", "VETO"]
    is_valid: bool
    reason: str
    violated_windows: List[Dict[str, Any]] = Field(default_factory=list)


class SlotAgent:
    """Hard veto agent validating airport movement capacity and night curfews."""

    def __init__(self, hub_airport: Optional[str] = None):
        self.hub = hub_airport or settings.HUB_AIRPORT

    def evaluate_candidate_plan(
        self,
        candidate: CandidatePlan,
        base_schedule: List[Dict[str, Any]],
        slot_windows: List[Dict[str, Any]],
        run_id: str,
        round_number: int = 1
    ) -> SlotEvaluationResult:
        """Validates slot window capacities. Can issue binding HARD VETO."""
        mutated_res = apply_plan_diff(base_schedule, candidate.plan_diff)
        mutated_schedule = mutated_res["mutated_flights"]

        res = check_slot(self.hub, mutated_schedule, slot_windows)

        from skymediator.llm import synthesize_slot_rationale, is_gemini_available

        if not res["is_valid"]:
            first_v = res["violated_windows"][0]
            reason = first_v.get("reason", "Airport slot window capacity exceeded during low visibility.")
            if is_gemini_available():
                llm_reason = synthesize_slot_rationale(self.hub, False, res["violated_windows"], candidate.plan_id)
                if llm_reason and not llm_reason.startswith("[Deterministic"):
                    reason = llm_reason

            logger.warning(f"Slot Agent issued HARD VETO on {candidate.plan_id}: {reason}")

            span = TraceSpan(
                span_id=f"SLOT-{uuid4().hex[:6]}",
                run_id=run_id,
                round=round_number,
                agent="SlotAgent",
                action_type="VETO_EMITTED",
                tool_name="check_slot",
                input_payload={"hub": self.hub, "plan_id": candidate.plan_id},
                output_payload=res
            )
            write_trace_span(span)

            return SlotEvaluationResult(
                decision="VETO",
                is_valid=False,
                reason=reason,
                violated_windows=res["violated_windows"]
            )

        pass_reason = "All flight movements satisfy runway slot capacities and night curfews."
        if is_gemini_available():
            llm_pass = synthesize_slot_rationale(self.hub, True, [], candidate.plan_id)
            if llm_pass and not llm_pass.startswith("[Deterministic"):
                pass_reason = llm_pass

        return SlotEvaluationResult(
            decision="PASS",
            is_valid=True,
            reason=pass_reason
        )
