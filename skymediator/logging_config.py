"""
Structured logging and trace recording for SkyMediator.
Outputs human-readable console logs and writes structured JSONL trace spans.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from skymediator.config import settings


class TraceSpan(BaseModel):
    span_id: str
    run_id: str
    round: int
    agent: str
    action_type: str  # "AGENT_INVOCATION", "TOOL_CALL", "VETO_EMITTED", "INTERRUPT_PAUSE", "HUMAN_INPUT"
    tool_name: Optional[str] = None
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tokens_used: int = 0
    latency_ms: float = 0.0


def setup_logger(name: str = "skymediator") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = setup_logger()


def map_span_to_event(span: TraceSpan):
    from skymediator.events import AgentEvent
    action = span.action_type.upper()
    event_type = "agent_message"
    status = "INFO"
    recipient = "Mediator"

    if "VETO" in action:
        event_type = "plan_vetoed"
        status = "VETO"
        recipient = "Rotation"
    elif "PROPOSE" in action:
        event_type = "proposal_created"
        status = "SUCCESS"
        recipient = "CrewLegality"
    elif "INITIALIZE" in action:
        event_type = "disruption_detected"
        status = "INFO"
        recipient = "Sentinel"
    elif "ADJUDICATE" in action:
        out_stat = span.output_payload.get("status")
        if out_stat == "READY_FOR_APPROVAL":
            event_type = "recommendation_created"
            status = "SUCCESS"
            recipient = "DutyManager"
        elif out_stat == "ESCALATE":
            event_type = "workflow_escalated"
            status = "WARNING"
            recipient = "DutyManager"
        else:
            event_type = "plan_ranked"
            status = "INFO"
            recipient = "Rotation"
    elif "TOOL" in action:
        event_type = "tool_completed"
        status = "INFO"
    elif "PARSE" in action:
        event_type = "message_parsed"
        status = "INFO"
        recipient = "Sentinel"

    summary = ""
    if span.tool_name:
        summary = f"Tool '{span.tool_name}' called by {span.agent}"
    elif span.output_payload.get("operational_rationale"):
        summary = span.output_payload["operational_rationale"]
    elif span.output_payload.get("reason"):
        summary = span.output_payload["reason"]
    elif span.output_payload.get("status"):
        summary = f"{span.agent}: {span.output_payload.get('status')}"
    else:
        summary = f"{span.agent} performed {span.action_type}"

    plan_id = span.input_payload.get("plan_id") or span.output_payload.get("plan_id")

    payload = {
        "span_id": span.span_id,
        "tool_name": span.tool_name,
        "input_payload": span.input_payload,
        "output_payload": span.output_payload,
        "latency_ms": span.latency_ms,
        "tokens_used": span.tokens_used
    }

    return AgentEvent(
        event_id=f"EVT-{span.span_id}",
        run_id=span.run_id,
        timestamp_utc=span.timestamp,
        plan_id=plan_id,
        round_number=span.round,
        event_type=event_type,
        actor=span.agent,
        recipient=recipient,
        status=status,
        summary=summary,
        structured_payload=payload,
        correlation_id=span.span_id
    )


def write_trace_span(span: TraceSpan, target_dir: Optional[Path] = None) -> Path:
    """Appends a validated TraceSpan into a run-specific JSONL trace file and notifies event broker."""
    out_dir = target_dir or settings.TRACES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_file = out_dir / f"run_{span.run_id}.jsonl"
    
    with open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(span.model_dump(), default=str) + "\n")

    # Bridge to real-time event broker and SQLite persistence
    try:
        from skymediator.events import broker
        event = map_span_to_event(span)
        broker.publish(event, persist=True)
    except Exception as e:
        logger.error(f"Event bridge notice: {e}")
        
    return trace_file
