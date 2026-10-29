"""
Crew Legality Agent — Statutory FDTL Enforcement and Agentic RAG.
Evaluates crew duty against DGCA CAR Section 7, Series J, Part III.
Holds absolute HARD VETO authority.
Uses Agentic RAG: retrieves clauses, self-grades relevance, rewrites queries, and abstains if ambiguous.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.ingest.build_rules_index import retrieve_fdtl
from skymediator.logging_config import TraceSpan, write_trace_span, logger
from skymediator.models import CandidatePlan
from skymediator.tools.duty import calc_duty_time
from skymediator.tools.schedule import apply_plan_diff


class CrewEvaluationResult(BaseModel):
    decision: Literal["PASS", "VETO", "ABSTAIN"]
    is_legal: bool
    cited_clause: Optional[str] = None
    retrieval_confidence: float = 1.0
    reason: str
    violations: List[Dict[str, Any]] = Field(default_factory=list)


class CrewLegalityAgent:
    """Hard veto agent validating crew flight duty limitations and statutory rest."""

    def __init__(self, fdtl_version: Optional[str] = None):
        self.fdtl_version = fdtl_version or settings.FDTL_VERSION

    def evaluate_candidate_plan(
        self,
        candidate: CandidatePlan,
        base_schedule: List[Dict[str, Any]],
        active_crew: List[Dict[str, Any]],
        run_id: str,
        round_number: int = 1
    ) -> CrewEvaluationResult:
        """Evaluates statutory legality of the candidate plan. Can issue binding HARD VETO."""
        mutated_res = apply_plan_diff(base_schedule, candidate.plan_diff)
        mutated_schedule = mutated_res["mutated_flights"]

        for crew in active_crew:
            crew_id = crew["crew_id"]
            assigned_flights = crew.get("assigned_flights", [])
            duty_record = crew.get("duty_record", {
                "duty_start": datetime(2026, 11, 1, 4, 0).isoformat()
            })

            calc_res = calc_duty_time(
                crew_id=crew_id,
                mutated_schedule=mutated_schedule,
                crew_duty_record=duty_record,
                assigned_flight_ids=assigned_flights,
                fdtl_version=self.fdtl_version
            )

            if not calc_res["is_legal"]:
                violation = calc_res["violations"][0]
                violation_type = violation.get("type")

                # --- AGENTIC RAG RETRIEVAL LOOP ---
                initial_query = f"DGCA CAR FDTL rule for {violation_type} with actual {violation.get('actual_minutes')}m limit {violation.get('limit_minutes')}m"
                retrieved_clauses = retrieve_fdtl(initial_query, k=2)

                # Self-Grade Retrieval Relevance
                top_clause = retrieved_clauses[0] if retrieved_clauses else None
                relevance_score = top_clause.get("score", 0.0) if top_clause else 0.0

                if relevance_score < 0.65:
                    # Self-Query Rewrite: Reformulate with formal regulatory keywords via Gemini LLM
                    from skymediator.llm import reformulate_statutory_query
                    rewritten_query = reformulate_statutory_query(initial_query, violation_type or "FDTL exceedance")
                    retrieved_clauses = retrieve_fdtl(rewritten_query, k=2)
                    top_clause = retrieved_clauses[0] if retrieved_clauses else None
                    relevance_score = top_clause.get("score", 0.0) if top_clause else 0.0

                clause_id = top_clause.get("clause_id", violation.get("clause_id")) if top_clause else violation.get("clause_id")

                # If retrieval completely fails on an ambiguous edge case -> ABSTAIN
                if not top_clause and relevance_score < 0.30:
                    logger.warning(f"Crew Legality ABSTAINED on {candidate.plan_id}: Ambiguous statutory clause.")
                    return CrewEvaluationResult(
                        decision="ABSTAIN",
                        is_legal=False,
                        retrieval_confidence=relevance_score,
                        reason="Ambiguous statutory regulation or unindexed clause. Escalated to Duty Manager.",
                        violations=calc_res["violations"]
                    )

                from skymediator.llm import explain_crew_legality_reasoning
                legal_explanation = explain_crew_legality_reasoning(
                    crew_id=crew_id,
                    is_legal=False,
                    violation=violation,
                    cited_clause=clause_id
                )
                veto_reason = legal_explanation if legal_explanation and not legal_explanation.startswith("[Deterministic") else violation["reason"]

                logger.warning(f"Crew Legality issued HARD VETO on {candidate.plan_id} for crew {crew_id}: {veto_reason}")

                span = TraceSpan(
                    span_id=f"CREW-{uuid4().hex[:6]}",
                    run_id=run_id,
                    round=round_number,
                    agent="CrewLegality",
                    action_type="VETO_EMITTED",
                    tool_name="calc_duty_time",
                    input_payload={"crew_id": crew_id, "plan_id": candidate.plan_id, "rag_query": initial_query},
                    output_payload={"violation": violation, "cited_clause": clause_id, "confidence": relevance_score, "statutory_explanation": veto_reason}
                )
                write_trace_span(span)

                return CrewEvaluationResult(
                    decision="VETO",
                    is_legal=False,
                    cited_clause=clause_id,
                    retrieval_confidence=relevance_score,
                    reason=veto_reason,
                    violations=calc_res["violations"]
                )

        # Plan satisfies all FDTL limits
        return CrewEvaluationResult(
            decision="PASS",
            is_legal=True,
            reason="All assigned flight duty periods, block hours, and rest buffers satisfy DGCA CAR Section 7."
        )
