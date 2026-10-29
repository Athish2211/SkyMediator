"""
Rotation Agent — Aircraft Rotation and Operational Schedule Proposer.
Formulates candidate recovery plans (tail swaps, delays, cancellations, crew deadheading)
and synthesizes legal counter-proposals based on constraint feedback.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan, DelayOp, SwapTailOp, CancelOp, RepositionCrewOp
from skymediator.tools.schedule import swap_tail, check_range_maint


class RotationAgent:
    """Operational architect formulating schedule mutations expressed as PlanDiffOps."""

    def propose_candidate_plan(
        self,
        round_number: int,
        disruption: Dict[str, Any],
        base_schedule: List[Dict[str, Any]],
        constraints_log: List[Dict[str, Any]],
        run_id: str
    ) -> CandidatePlan:
        """Generates a candidate plan or counter-proposal tailored to active constraints."""
        affected_id = disruption.get("affected_flight_id", "6E-101")
        flight_base = next((f for f in base_schedule if f["flight_id"] == affected_id), None)
        std_dt = datetime.fromisoformat(flight_base["std"]) if flight_base else datetime(2026, 11, 1, 6, 0)
        sta_dt = datetime.fromisoformat(flight_base["sta"]) if flight_base else datetime(2026, 11, 1, 8, 30)

        plan_diff: List[Any] = []
        rationale = ""

        # Identify which constraints were violated in prior rounds
        vetoed_types = [c.get("constraint_type") for c in constraints_log]

        # Check for Human Replan Directive (PROP-04 Replan Loop)
        human_revisions = [c for c in constraints_log if c.get("constraint_type") == "HUMAN_REVISION"]
        stacked = disruption.get("stacked_disruptions") or []

        if human_revisions:
            latest_hr = human_revisions[-1]
            feedback = (latest_hr.get("reason") or "").lower()
            import re

            has_cancel = any(w in feedback for w in ["cancel", "cancellation"])
            has_delay = any(w in feedback for w in ["delay", "postpone", "push", "retard", "hold"])
            has_swap = any(w in feedback for w in ["swap", "standby", "reassign"]) or ("tail" in feedback and "swap" in feedback)

            # Determine dominant human directive action resolving "instead of" precedence
            target_action = None
            if has_delay and has_swap:
                idx_delay = min((feedback.find(w) for w in ["delay", "postpone", "push", "retard", "hold"] if w in feedback), default=999)
                idx_swap = min((feedback.find(w) for w in ["swap", "standby", "reassign"] if w in feedback), default=999)
                target_action = "delay" if idx_delay < idx_swap else "swap"
            elif has_cancel:
                target_action = "cancel"
            elif has_delay:
                target_action = "delay"
            elif has_swap or "tail" in feedback or "standby" in feedback:
                target_action = "swap"

            if target_action == "cancel":
                plan_diff = [
                    CancelOp(
                        flight_id=affected_id,
                        reason=f"Duty Manager Replan Directive: Cancel flight {affected_id} per instructions: '{latest_hr.get('reason')}'"
                    ).model_dump()
                ]
                rationale = f"Replan revision: Cancelled flight {affected_id} per Duty Manager explicit directive."

            elif target_action == "swap":
                tail_match = re.search(r"VT-[A-Z0-9]+", latest_hr.get("reason", "").upper())
                target_tail = tail_match.group(0) if tail_match else disruption.get("candidate_tail", "VT-BLR15")
                val = swap_tail(affected_id, target_tail, base_schedule)
                plan_diff = [
                    SwapTailOp(
                        flight_id=affected_id,
                        original_tail=disruption.get("original_tail", flight_base["tail"] if flight_base else "VT-BLR01"),
                        new_tail=target_tail,
                        reason=f"Duty Manager Replan Directive: Reassign flight to {target_tail} per '{latest_hr.get('reason')}'"
                    ).model_dump()
                ]
                rationale = f"Replan revision: Swapped {affected_id} to standby tail {target_tail} (Turnaround: {val.get('turnaround_margin_minutes', 0)}m) per Duty Manager instruction."

            elif target_action == "delay":
                digits = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)?", feedback)
                d_min = int(digits.group(1)) if digits else 45
                plan_diff = [
                    DelayOp(
                        flight_id=affected_id,
                        delay_minutes=d_min,
                        new_std=std_dt + timedelta(minutes=d_min),
                        new_sta=sta_dt + timedelta(minutes=d_min),
                        reason=f"Duty Manager Replan Directive: Calibrated {d_min}m delay per '{latest_hr.get('reason')}'"
                    ).model_dump()
                ]
                rationale = f"Replan revision: Rescheduled {affected_id} with {d_min}m delay per Duty Manager directive."

            else:
                # Switch strategy from previous candidate to counter-propose
                target_tail = disruption.get("candidate_tail", "VT-BLR15")
                val = swap_tail(affected_id, target_tail, base_schedule)
                plan_diff = [
                    SwapTailOp(
                        flight_id=affected_id,
                        original_tail=disruption.get("original_tail", flight_base["tail"] if flight_base else "VT-BLR01"),
                        new_tail=target_tail,
                        reason=f"Duty Manager Replan Directive: '{latest_hr.get('reason')}'. Swapped to preserve schedule integrity."
                    ).model_dump()
                ]
                rationale = f"Replan revision addressing Duty Manager directive '{latest_hr.get('reason')}': Swapped {affected_id} to {target_tail} to maintain punctuality."

        elif len(stacked) > 1:
            # Multi-incident disruption stacking: Formulate recovery mutations for ALL active disruptions simultaneously
            plan_diff = []
            assigned_tails = set()
            for disc in stacked:
                f_id = disc.get("affected_flight_id")
                if not f_id:
                    continue
                fb = next((f for f in base_schedule if f["flight_id"] == f_id), None)
                f_std = datetime.fromisoformat(fb["std"]) if fb else datetime(2026, 11, 1, 6, 0)
                f_sta = datetime.fromisoformat(fb["sta"]) if fb else datetime(2026, 11, 1, 8, 30)
                orig_t = disc.get("original_tail", fb["tail"] if fb else "VT-BLR01")

                if disc.get("initial_action") == "cancel":
                    plan_diff.append(
                        CancelOp(
                            flight_id=f_id,
                            reason=f"Stacked recovery: Cancel flight {f_id} to isolate disruption"
                        ).model_dump()
                    )
                elif disc.get("initial_action") == "swap_tail" or disc.get("type") in ("MAINTENANCE", "AOG"):
                    cand_t = disc.get("candidate_tail", "VT-BLR15")
                    if cand_t in assigned_tails:
                        cand_t = "VT-BLR14" if cand_t != "VT-BLR14" else "VT-BLR13"
                    assigned_tails.add(cand_t)
                    plan_diff.append(
                        SwapTailOp(
                            flight_id=f_id,
                            original_tail=orig_t,
                            new_tail=cand_t,
                            reason=f"Stacked recovery: Aircraft swap for {f_id} to standby tail {cand_t}"
                        ).model_dump()
                    )
                else:
                    d_mins = disc.get("counter_delay_minutes") or disc.get("delay_minutes", 30)
                    if d_mins > 90 and round_number > 1:
                        d_mins = 35
                    plan_diff.append(
                        DelayOp(
                            flight_id=f_id,
                            delay_minutes=d_mins,
                            new_std=f_std + timedelta(minutes=d_mins),
                            new_sta=f_sta + timedelta(minutes=d_mins),
                            reason=f"Stacked recovery: Calibrated {d_mins}m delay for {f_id}"
                        ).model_dump()
                    )

            flight_ids_str = ", ".join(d.get("affected_flight_id", "") for d in stacked if d.get("affected_flight_id"))
            rationale = f"Multi-Incident Recovery Plan covering {len(stacked)} stacked disruptions ({flight_ids_str}). Formulated coordinated schedule mutations."

        elif round_number == 1:
            if disruption.get("initial_action") == "cancel":
                plan_diff = [
                    CancelOp(
                        flight_id=affected_id,
                        reason=f"Round 1: Strategic cancellation per Duty Manager directive: {disruption.get('raw_message', 'Disruption mitigation')}"
                    ).model_dump()
                ]
                rationale = f"Cancel flight {affected_id} per Duty Manager operational dispatch directive."
            elif disruption.get("initial_action") == "excessive_delay":
                delay_min = disruption.get("delay_minutes", 180)
                plan_diff = [
                    DelayOp(
                        flight_id=affected_id,
                        delay_minutes=delay_min,
                        new_std=std_dt + timedelta(minutes=delay_min),
                        new_sta=sta_dt + timedelta(minutes=delay_min),
                        reason=f"Round 1: Initial tactical delay of {delay_min}m for weather/operational clearance"
                    ).model_dump()
                ]
                rationale = f"Delay flight {affected_id} by {delay_min}m to allow runway visual range recovery."
            else:
                target_tail = disruption.get("candidate_tail", "VT-BLR15")
                # Validate turnaround before proposing swap
                val = swap_tail(affected_id, target_tail, base_schedule)
                plan_diff = [
                    SwapTailOp(
                        flight_id=affected_id,
                        original_tail=disruption.get("original_tail", flight_base["tail"] if flight_base else "VT-BLR01"),
                        new_tail=target_tail,
                        reason="Swap to available standby tail to maintain scheduled departure"
                    ).model_dump()
                ]
                rationale = f"Swap aircraft on flight {affected_id} to standby tail {target_tail} (Turnaround: {val.get('turnaround_margin_minutes', 0)}m)."

        elif "FDTL" in vetoed_types:
            # Counter-proposal responding to Crew Legality Veto:
            # Check if cancellation or moderate delay was requested
            if disruption.get("counter_action") == "cancel":
                plan_diff = [
                    CancelOp(
                        flight_id=affected_id,
                        reason="Counter-proposal responding to Crew FDTL veto: Cancel flight to prevent illegal duty exceedance"
                    ).model_dump()
                ]
                rationale = f"Counter-proposal: Selectively cancel {affected_id} to respect statutory crew duty limits."
            else:
                counter_delay = disruption.get("counter_delay_minutes", 25)
                plan_diff = [
                    DelayOp(
                        flight_id=affected_id,
                        delay_minutes=counter_delay,
                        new_std=std_dt + timedelta(minutes=counter_delay),
                        new_sta=sta_dt + timedelta(minutes=counter_delay),
                        reason=f"Counter-proposal: Reduced delay of {counter_delay}m calibrated within legal crew FDP"
                    ).model_dump()
                ]
                rationale = f"Counter-proposal: Calibrated {counter_delay}m delay for {affected_id} preserving pilot legality."

        elif "SLOT" in vetoed_types:
            # Counter-proposal responding to Slot capacity / Curfew Veto:
            plan_diff = [
                CancelOp(
                    flight_id=affected_id,
                    reason="Counter-proposal responding to Slot veto: Cancel flight to eliminate slot window overflow"
                ).model_dump()
            ]
            rationale = f"Counter-proposal: Cancel {affected_id} to relieve slot saturation."

        else:
            # Default fallback
            plan_diff = [
                DelayOp(
                    flight_id=affected_id,
                    delay_minutes=30,
                    new_std=std_dt + timedelta(minutes=30),
                    new_sta=sta_dt + timedelta(minutes=30),
                    reason="Tactical 30m delay"
                ).model_dump()
            ]
            rationale = f"Apply 30m delay on {affected_id}."

        from skymediator.llm import synthesize_rotation_rationale, is_gemini_available
        if plan_diff:
            llm_rationale = synthesize_rotation_rationale(
                round_number=round_number,
                disruption=disruption,
                chosen_op=plan_diff[0],
                constraints_feedback=[c.get("reason") for c in constraints_log if c.get("reason")]
            )
            if llm_rationale and not llm_rationale.startswith("[Deterministic"):
                rationale = llm_rationale

        proposer_label = "Rotation (Gemini LLM)" if is_gemini_available() else "Rotation"

        candidate = CandidatePlan(
            plan_id=f"PLAN-R{round_number}-{uuid4().hex[:4]}",
            round_created=round_number,
            proposing_agent=proposer_label,
            plan_diff=plan_diff,
            operational_rationale=rationale
        )

        span = TraceSpan(
            span_id=f"ROT-{uuid4().hex[:6]}",
            run_id=run_id,
            round=round_number,
            agent="Rotation",
            action_type="PROPOSE_RECOVERY",
            input_payload={"round": round_number, "constraints": [c.get("reason") for c in constraints_log]},
            output_payload=candidate.model_dump()
        )
        write_trace_span(span)

        return candidate
