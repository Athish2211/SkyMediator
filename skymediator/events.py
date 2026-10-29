"""
Real-Time Event Broker & Persistence Engine for SkyMediator.
Enables live streaming (SSE) to the Agent Operations Console, structured event history,
and persistent decision audit logging in SQLite.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from pydantic import BaseModel, Field

from skymediator.config import settings
from skymediator.db import get_connection
from skymediator.logging_config import logger


class AgentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"EVT-{uuid4().hex[:8].upper()}")
    run_id: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    disruption_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_revision: int = 1
    round_number: int = 1
    event_type: str  # e.g., "disruption_detected", "agent_message", "plan_vetoed", "recommendation_created"
    actor: str       # "Sentinel", "Rotation", "CrewLegality", "Slot", "Passenger", "Cost", "Mediator", "DutyManager", "System"
    recipient: Optional[str] = None
    status: str = "INFO"  # "INFO", "SUCCESS", "VETO", "WARNING", "ERROR"
    summary: str
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None

    def to_db_row(self) -> tuple:
        return (
            self.event_id,
            self.run_id,
            self.disruption_id,
            self.plan_id,
            self.plan_revision,
            self.round_number,
            self.event_type,
            self.actor,
            self.recipient,
            self.status,
            self.summary,
            json.dumps(self.structured_payload, default=str),
            self.correlation_id,
            self.timestamp_utc,
        )


class EventBroker:
    """
    Central event broker delivering live events to SSE subscribers and
    persisting them into the SQLite agent_events table.
    """

    def __init__(self):
        # Maps subscriber queue to optional filter run_id
        self._subscribers: Dict[asyncio.Queue, Optional[str]] = {}
        try:
            loop = asyncio.get_running_loop()
            self._lock = asyncio.Lock() if loop and loop.is_running() else None
        except RuntimeError:
            self._lock = None

    def subscribe(self, run_id: Optional[str] = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers[q] = run_id
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            del self._subscribers[q]

    def publish(self, event: AgentEvent, persist: bool = True, db_path: Optional[str] = None) -> None:
        """
        Publishes an event to active subscribers and persists it in SQLite.
        Thread-safe across async loops and sync background workers.
        """
        if persist:
            self._persist_event(event, db_path)

        # Notify active SSE subscribers
        stale_queues: List[asyncio.Queue] = []
        for q, filter_run in list(self._subscribers.items()):
            if filter_run and filter_run != event.run_id:
                continue
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                stale_queues.append(q)
            except Exception as e:
                logger.warning(f"Error publishing to subscriber queue: {e}")
                stale_queues.append(q)

        for q in stale_queues:
            self.unsubscribe(q)

    def _persist_event(self, event: AgentEvent, db_path: Optional[str] = None) -> None:
        conn = get_connection(db_path or settings.DB_PATH)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO agent_events (
                    event_id, run_id, disruption_id, plan_id, plan_revision, round_number,
                    event_type, actor, recipient, status, summary, structured_payload,
                    correlation_id, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                event.to_db_row()
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist agent event {event.event_id}: {e}")
        finally:
            conn.close()

    def get_events(
        self,
        run_id: Optional[str] = None,
        actor: Optional[str] = None,
        event_type: Optional[str] = None,
        round_number: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        since_id: Optional[str] = None,
        db_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries historical events from SQLite with structured filtering and pagination."""
        conn = get_connection(db_path or settings.DB_PATH)
        try:
            query = "SELECT * FROM agent_events WHERE 1=1"
            params: List[Any] = []

            if run_id:
                query += " AND run_id = ?"
                params.append(run_id)
            if actor:
                query += " AND actor = ?"
                params.append(actor)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            if round_number is not None:
                query += " AND round_number = ?"
                params.append(round_number)
            if since_id:
                query += " AND rowid > (SELECT rowid FROM agent_events WHERE event_id = ?)"
                params.append(since_id)

            query += " ORDER BY timestamp_utc ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                if d.get("structured_payload"):
                    try:
                        d["structured_payload"] = json.loads(d["structured_payload"])
                    except Exception:
                        pass
                rows.append(d)

            # If no SQLite events recorded yet for this run_id, check and sync from run JSONL trace file
            if run_id and len(rows) == 0:
                trace_file = settings.TRACES_DIR / f"run_{run_id}.jsonl"
                if trace_file.exists():
                    from skymediator.logging_config import TraceSpan, map_span_to_event
                    with open(trace_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                span_data = json.loads(line)
                                span = TraceSpan.model_validate(span_data)
                                ev = map_span_to_event(span)
                                conn.execute(
                                    """INSERT OR REPLACE INTO agent_events (
                                        event_id, run_id, disruption_id, plan_id, plan_revision, round_number,
                                        event_type, actor, recipient, status, summary, structured_payload,
                                        correlation_id, timestamp_utc
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    ev.to_db_row()
                                )
                            except Exception:
                                pass
                    conn.commit()
                    # Re-query
                    cursor = conn.execute(query, params)
                    rows = []
                    for r in cursor.fetchall():
                        d = dict(r)
                        if d.get("structured_payload"):
                            try:
                                d["structured_payload"] = json.loads(d["structured_payload"])
                            except Exception:
                                pass
                        rows.append(d)

            return rows
        finally:
            conn.close()


# Global Singleton Broker
broker = EventBroker()


def record_plan_revision(
    candidate: Dict[str, Any],
    run_id: str,
    round_number: int,
    db_path: Optional[str] = None
) -> int:
    """Persists a snapshot of a plan revision into the plan_revisions table."""
    conn = get_connection(db_path or settings.DB_PATH)
    try:
        plan_id = candidate.get("plan_id", f"PLAN-R{round_number}")
        proposing_agent = candidate.get("proposing_agent", "Rotation")
        rationale = candidate.get("operational_rationale", "")
        plan_diff = json.dumps(candidate.get("plan_diff", []), default=str)
        is_feasible = 1 if (len(candidate.get("vetoed_by", [])) == 0 and candidate.get("is_feasible", True)) else 0
        vetoed_by = json.dumps(candidate.get("vetoed_by", []))
        veto_reasons = json.dumps(candidate.get("veto_reasons", {}))
        scores = json.dumps(candidate.get("scores", {}))
        compliance_notes = json.dumps(candidate.get("compliance_notes", {}))

        cursor = conn.execute(
            """INSERT INTO plan_revisions (
                run_id, plan_id, round_number, proposing_agent, operational_rationale,
                plan_diff_json, is_feasible, vetoed_by_json, veto_reasons_json, scores_json, compliance_notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, plan_id, round_number, proposing_agent, rationale, plan_diff, is_feasible, vetoed_by, veto_reasons, scores, compliance_notes)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def record_decision(
    decision: Dict[str, Any],
    db_path: Optional[str] = None
) -> str:
    """Persists a Duty Manager decision record into SQLite."""
    conn = get_connection(db_path or settings.DB_PATH)
    try:
        dec_id = decision.get("decision_id") or f"DEC-{uuid4().hex[:8].upper()}"
        run_id = decision["run_id"]
        disruption_id = decision.get("disruption_id")
        plan_id = decision.get("plan_id")
        round_number = decision.get("round_number", 1)
        action = decision.get("duty_manager_action", "APPROVED")
        manager_id = decision.get("duty_manager_id", "Athish Raj (Duty Manager)")
        notes = decision.get("duty_manager_notes", "")
        timestamp = decision.get("decision_timestamp") or datetime.now(timezone.utc).isoformat()
        diff_json = json.dumps(decision.get("proposed_diff", []), default=str)
        validation_json = json.dumps(decision.get("validation_outcomes", {}), default=str)
        vetoed_by_json = json.dumps(decision.get("vetoed_by", []))
        is_feasible = 1 if decision.get("is_feasible_at_decision", True) else 0
        mediator_rationale = decision.get("mediator_rationale", "")
        final_status = decision.get("final_status", "RECORDED")

        conn.execute(
            """INSERT INTO decision_records (
                decision_id, run_id, disruption_id, plan_id, round_number,
                duty_manager_action, duty_manager_id, duty_manager_notes,
                decision_timestamp, proposed_diff_json, validation_outcomes_json,
                vetoed_by_json, is_feasible_at_decision, mediator_rationale, final_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dec_id, run_id, disruption_id, plan_id, round_number,
                action, manager_id, notes, timestamp, diff_json, validation_json,
                vetoed_by_json, is_feasible, mediator_rationale, final_status
            )
        )
        conn.commit()
        return dec_id
    finally:
        conn.close()

