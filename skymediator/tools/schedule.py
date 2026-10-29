"""
Deterministic schedule query and mutation tools (resolving GAP-01 & PROP-01).
Provides pure functional mutations without database side-effects.
"""

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from skymediator.config import settings
from skymediator.db import get_connection
from skymediator.models import PlanDiffOp


def query_schedule(
    flight_ids: Optional[List[str]] = None,
    airport: Optional[str] = None,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    db_path: Optional[Union[str, Path]] = None
) -> List[Dict[str, Any]]:
    """Deterministic query of flight schedule rows from SQLite."""
    conn = get_connection(db_path)
    try:
        query = "SELECT flight_id, tail, origin, dest, std, sta, etd, eta, seats, status FROM flights WHERE 1=1"
        params: List[Any] = []
        
        if flight_ids:
            placeholders = ",".join("?" for _ in flight_ids)
            query += f" AND flight_id IN ({placeholders})"
            params.extend(flight_ids)
            
        if airport:
            query += " AND (origin = ? OR dest = ?)"
            params.extend([airport, airport])
            
        if window_start:
            query += " AND std >= ?"
            params.append(window_start.isoformat())
            
        if window_end:
            query += " AND std <= ?"
            params.append(window_end.isoformat())
            
        query += " ORDER BY std ASC"
        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        return rows
    finally:
        conn.close()


def apply_plan_diff(
    base_schedule: List[Dict[str, Any]],
    plan_diff: List[Union[PlanDiffOp, Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Pure deterministic application of PlanDiffOp mutations to a base schedule.
    Produces an in-memory mutated schedule for downstream validation without touching SQLite.
    """
    mutated = [deepcopy(flight) for flight in base_schedule]
    flight_map = {f["flight_id"]: f for f in mutated}
    applied_count = 0
    conflicts: List[str] = []

    for op in plan_diff:
        op_dict = op if isinstance(op, dict) else op.model_dump()
        op_type = op_dict.get("op")
        flight_id = op_dict.get("flight_id")

        if flight_id not in flight_map:
            conflicts.append(f"Target flight_id {flight_id} not found in schedule")
            continue

        flight = flight_map[flight_id]

        if op_type == "swap_tail":
            flight["tail"] = op_dict["new_tail"]
            applied_count += 1

        elif op_type == "delay":
            new_std = op_dict["new_std"]
            new_sta = op_dict["new_sta"]
            flight["etd"] = new_std.isoformat() if isinstance(new_std, datetime) else str(new_std)
            flight["eta"] = new_sta.isoformat() if isinstance(new_sta, datetime) else str(new_sta)
            flight["status"] = "DELAYED"
            applied_count += 1

        elif op_type == "cancel":
            flight["status"] = "CANCELLED"
            applied_count += 1

        elif op_type == "reposition_crew":
            # Repositioning records are handled in crew roster mutation
            applied_count += 1

        else:
            conflicts.append(f"Unknown operation type: {op_type}")

    return {
        "mutated_flights": mutated,
        "applied_ops_count": applied_count,
        "unresolved_conflicts": conflicts
    }


def swap_tail(
    flight_id: str,
    new_tail: str,
    schedule: List[Dict[str, Any]],
    min_turn_min: int = 35
) -> Dict[str, Any]:
    """
    Validates physical turnaround continuity for an aircraft tail swap.
    Verifies that the new tail arrives at the origin at least min_turn_min before departure.
    """
    flight_map = {f["flight_id"]: f for f in schedule}
    if flight_id not in flight_map:
        return {"is_valid": False, "reasons": [f"Flight {flight_id} not found"]}

    target_flight = flight_map[flight_id]
    target_dep = datetime.fromisoformat(target_flight.get("etd") or target_flight["std"])
    origin = target_flight["origin"]

    # Find prior flights flown by new_tail
    prior_flights = [
        f for f in schedule 
        if f["tail"] == new_tail and f["flight_id"] != flight_id
        and datetime.fromisoformat(f.get("eta") or f["sta"]) <= target_dep
    ]

    if not prior_flights:
        # Aircraft is stationed idle at base or outstation
        return {
            "is_valid": True,
            "turnaround_margin_minutes": 999,
            "reasons": [f"Tail {new_tail} is idle prior to flight {flight_id}"]
        }

    # Last flight before target departure
    last_flight = max(prior_flights, key=lambda f: datetime.fromisoformat(f.get("eta") or f["sta"]))
    last_arrival = datetime.fromisoformat(last_flight.get("eta") or last_flight["sta"])
    last_dest = last_flight["dest"]

    if last_dest != origin:
        return {
            "is_valid": False,
            "turnaround_margin_minutes": -1,
            "reasons": [f"Tail {new_tail} arrives at {last_dest}, but flight {flight_id} departs from {origin}"]
        }

    turnaround_minutes = int((target_dep - last_arrival).total_seconds() / 60)
    is_valid = turnaround_minutes >= min_turn_min

    return {
        "is_valid": is_valid,
        "turnaround_margin_minutes": turnaround_minutes,
        "reasons": [] if is_valid else [
            f"Insufficient turnaround: {turnaround_minutes}m provided, {min_turn_min}m required"
        ]
    }


def check_range_maint(
    tail: str,
    flight_id: str,
    db_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Validates that tail has sufficient maintenance hours remaining."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT maintenance_due_hours FROM aircraft WHERE tail = ?",
            (tail,)
        )
        row = cursor.fetchone()
        if not row:
            return {"is_valid": False, "reasons": [f"Tail {tail} not found in database"]}
            
        hours_remaining = float(row["maintenance_due_hours"])
        is_valid = hours_remaining >= 2.0  # At least 2 block hours remaining
        
        return {
            "is_valid": is_valid,
            "hours_to_maintenance": hours_remaining,
            "reasons": [] if is_valid else [f"Tail {tail} maintenance due in {hours_remaining}h (< 2h buffer)"]
        }
    finally:
        conn.close()
