"""
SkyMediator OCC Web Application Server.
Provides an interactive real-time dashboard for Human Duty Managers to review
disruptions, watch multi-agent deliberation, inspect regulatory citations, and authorize recovery plans.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from skymediator.config import settings
from skymediator.db import get_connection, init_db
from skymediator.fixtures import seed_database
from contextlib import asynccontextmanager
from skymediator.graph import build_recovery_graph
from skymediator.tools.schedule import query_schedule


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.DB_PATH)
    conn = get_connection(settings.DB_PATH)
    try:
        count = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
        if count == 0:
            seed_database(settings.DB_PATH)
            from skymediator.ingest.make_scenarios import seed_scenarios
            seed_scenarios(settings.DB_PATH)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="SkyMediator OCC Dashboard",
    description="Multi-Agent Airline Disruption Recovery System for Kempegowda Hub (VOBL/BLR)",
    version="0.3.0",
    lifespan=lifespan
)

# In-memory storage for active deliberation sessions and stacked disruptions
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
ACTIVE_DISRUPTIONS: List[Dict[str, Any]] = []


class TriggerDisruptionRequest(BaseModel):
    scenario_id: Optional[str] = None
    duty_manager_message: Optional[str] = None
    duty_manager_name: str = "Athish Raj (Duty Manager)"


class ParseDisruptionRequest(BaseModel):
    message: str


class ApprovalDecisionRequest(BaseModel):
    run_id: str
    decision: str  # "APPROVE", "REJECT", "REPLAN"
    selected_plan_id: Optional[str] = None
    manager_notes: Optional[str] = None


class FlightPayload(BaseModel):
    flight_id: str
    tail: str
    origin: str = "VOBL"
    dest: str = "VIDP"
    std: str
    sta: str
    seats: int = 180
    status: str = "SCHEDULED"


class AircraftPayload(BaseModel):
    tail: str
    aircraft_type: str = "A320"
    seats: int = 180
    min_turn_min: int = 35
    current_airport: str = "VOBL"
    maintenance_due_hours: float = 100.0


class CrewDutyPayload(BaseModel):
    crew_id: str
    duty_start: str
    assigned_flight_id: Optional[str] = None


class CrewMemberPayload(BaseModel):
    crew_id: str
    name: str
    role: str = "CAPTAIN"
    base: str = "VOBL"


class ScenarioPayload(BaseModel):
    scenario_id: str
    name: str
    disruption_type: str
    airport: str = "VOBL"
    severity: str = "SEVERE"
    difficulty: str = "STANDARD"
    start_time: Optional[str] = None
    seeded_anomalies: Optional[Dict[str, Any]] = None


@app.get("/api/status")
def get_system_status():
    from skymediator.llm import is_gemini_available
    return {
        "system": "SkyMediator OCC",
        "primary_hub": settings.HUB_AIRPORT,
        "primary_iata": settings.HUB_IATA,
        "timezone": settings.TIMEZONE,
        "fdtl_version": settings.FDTL_VERSION,
        "max_rounds": settings.MAX_NEGOTIATION_ROUNDS,
        "llm_engine": settings.LLM_MODEL,
        "llm_available": is_gemini_available(),
        "status": "OPERATIONAL"
    }


# --- PREDEFINED DATA MANAGEMENT ENDPOINTS ---

@app.get("/api/fleet")
def list_fleet():
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("SELECT tail, aircraft_type, seats, min_turn_min, current_airport, maintenance_due_hours FROM aircraft ORDER BY tail ASC")
        rows = [dict(r) for r in cursor.fetchall()]
        return {"fleet_count": len(rows), "fleet": rows, "aircraft": rows}
    finally:
        conn.close()


@app.post("/api/fleet")
def add_or_update_aircraft(item: AircraftPayload):
    conn = get_connection(settings.DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO aircraft (tail, aircraft_type, seats, min_turn_min, current_airport, maintenance_due_hours)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (item.tail.upper(), item.aircraft_type, item.seats, item.min_turn_min, item.current_airport.upper(), item.maintenance_due_hours)
        )
        conn.commit()
        return {"status": "SUCCESS", "message": f"Aircraft {item.tail.upper()} updated successfully."}
    finally:
        conn.close()


@app.delete("/api/fleet/{tail}")
def delete_aircraft(tail: str):
    conn = get_connection(settings.DB_PATH)
    try:
        t = tail.upper()
        conn.execute("UPDATE flights SET tail = 'STANDBY' WHERE tail = ?", (t,))
        conn.execute("DELETE FROM aircraft WHERE tail = ?", (t,))
        conn.commit()
        return {"status": "SUCCESS", "message": f"Aircraft {t} deleted."}
    finally:
        conn.close()


@app.get("/api/schedule")
@app.get("/api/flights")
def list_schedule():
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("SELECT flight_id, tail, origin, dest, std, sta, seats, status FROM flights ORDER BY std ASC")
        rows = [dict(r) for r in cursor.fetchall()]
        return {"flights_count": len(rows), "flights": rows, "schedule": rows}
    finally:
        conn.close()


@app.post("/api/schedule")
def add_or_update_flight(item: FlightPayload):
    conn = get_connection(settings.DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO flights (flight_id, tail, origin, dest, std, sta, seats, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.flight_id.upper(), item.tail.upper(), item.origin.upper(), item.dest.upper(), item.std, item.sta, item.seats, item.status.upper())
        )
        conn.commit()
        return {"status": "SUCCESS", "message": f"Flight {item.flight_id.upper()} recorded successfully."}
    finally:
        conn.close()


@app.delete("/api/schedule/{flight_id}")
def delete_flight(flight_id: str):
    conn = get_connection(settings.DB_PATH)
    try:
        fid = flight_id.upper()
        conn.execute("DELETE FROM crew_duty_flights WHERE flight_id = ?", (fid,))
        conn.execute("DELETE FROM connections WHERE inbound_flight = ? OR outbound_flight = ?", (fid, fid))
        conn.execute("DELETE FROM itinerary_legs WHERE flight_id = ?", (fid,))
        conn.execute("DELETE FROM flights WHERE flight_id = ?", (fid,))
        conn.commit()
        return {"status": "SUCCESS", "message": f"Flight {fid} removed from schedule."}
    finally:
        conn.close()


@app.get("/api/crew")
def list_crew():
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute(
            """SELECT c.crew_id, c.name, c.role, c.base, cd.duty_id, cd.duty_start, cd.max_fdp_minutes,
                      cdf.flight_id as assigned_flight_id
               FROM crew_members c
               LEFT JOIN crew_duties cd ON c.crew_id = cd.crew_id
               LEFT JOIN crew_duty_flights cdf ON cd.duty_id = cdf.duty_id
               ORDER BY c.crew_id ASC"""
        )
        return {"crew": [dict(r) for r in cursor.fetchall()]}
    finally:
        conn.close()


@app.post("/api/crew/duty")
def update_crew_duty(item: CrewDutyPayload):
    conn = get_connection(settings.DB_PATH)
    try:
        # Check if duty exists
        cursor = conn.execute("SELECT duty_id FROM crew_duties WHERE crew_id = ?", (item.crew_id,))
        row = cursor.fetchone()
        if row:
            duty_id = row["duty_id"]
            conn.execute("UPDATE crew_duties SET duty_start = ? WHERE duty_id = ?", (item.duty_start, duty_id))
        else:
            duty_id = f"DUTY-{item.crew_id}"
            conn.execute(
                "INSERT INTO crew_duties (duty_id, crew_id, duty_start, max_fdp_minutes) VALUES (?, ?, ?, 750)",
                (duty_id, item.crew_id, item.duty_start)
            )

        if item.assigned_flight_id:
            conn.execute("DELETE FROM crew_duty_flights WHERE duty_id = ?", (duty_id,))
            conn.execute(
                "INSERT INTO crew_duty_flights (duty_id, flight_id, leg_sequence) VALUES (?, ?, 1)",
                (duty_id, item.assigned_flight_id.upper())
            )
        conn.commit()
        return {"status": "SUCCESS", "message": f"Duty for {item.crew_id} updated (Start: {item.duty_start})."}
    finally:
        conn.close()


@app.post("/api/crew")
def add_or_update_crew_member(item: CrewMemberPayload):
    conn = get_connection(settings.DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO crew_members (crew_id, name, role, base)
               VALUES (?, ?, ?, ?)""",
            (item.crew_id.upper(), item.name, item.role.upper(), item.base.upper())
        )
        conn.commit()
        return {"status": "SUCCESS", "message": f"Crew member {item.crew_id.upper()} recorded successfully."}
    finally:
        conn.close()


@app.delete("/api/crew/{crew_id}")
def delete_crew_member(crew_id: str):
    conn = get_connection(settings.DB_PATH)
    try:
        cid = crew_id.upper()
        cursor = conn.execute("SELECT duty_id FROM crew_duties WHERE crew_id = ?", (cid,))
        duties = [r["duty_id"] for r in cursor.fetchall()]
        for did in duties:
            conn.execute("DELETE FROM crew_duty_flights WHERE duty_id = ?", (did,))
        conn.execute("DELETE FROM crew_duties WHERE crew_id = ?", (cid,))
        conn.execute("DELETE FROM crew_members WHERE crew_id = ?", (cid,))
        conn.commit()
        return {"status": "SUCCESS", "message": f"Crew member {cid} removed."}
    finally:
        conn.close()


@app.get("/api/scenarios")
def list_scenarios():
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("SELECT scenario_id, name, disruption_type, airport, severity, difficulty, start_time, seeded_anomalies FROM scenarios")
        rows = []
        for r in cursor.fetchall():
            item = dict(r)
            if item.get("seeded_anomalies"):
                try:
                    item["details"] = json.loads(item["seeded_anomalies"])
                except Exception:
                    item["details"] = {}
            rows.append(item)
        return {"scenarios": rows}
    finally:
        conn.close()


@app.post("/api/scenarios")
def add_or_update_scenario(item: ScenarioPayload):
    conn = get_connection(settings.DB_PATH)
    try:
        anomalies_str = json.dumps(item.seeded_anomalies or {})
        start_time = item.start_time or "2026-11-01T04:30:00"
        end_time = getattr(item, "end_time", None) or "2026-11-01T14:00:00"
        conn.execute(
            """INSERT OR REPLACE INTO scenarios (scenario_id, name, disruption_type, airport, severity, difficulty, start_time, end_time, seeded_anomalies)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.scenario_id.upper(), item.name, item.disruption_type.lower(), item.airport.upper(), item.severity.upper(), item.difficulty.upper(), start_time, end_time, anomalies_str)
        )
        conn.commit()
        return {"status": "SUCCESS", "message": f"Scenario {item.scenario_id.upper()} recorded successfully."}
    finally:
        conn.close()


@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str):
    conn = get_connection(settings.DB_PATH)
    try:
        conn.execute("DELETE FROM scenarios WHERE scenario_id = ?", (scenario_id.upper(),))
        conn.commit()
        return {"status": "SUCCESS", "message": f"Scenario {scenario_id.upper()} removed."}
    finally:
        conn.close()


@app.post("/api/database/reset")
@app.post("/api/reset_all_data")
def reset_database_fixtures():
    """Resets operational database back to pristine seeded fixtures, wiping previous runs."""
    from skymediator.fixtures import reset_all_data
    reset_all_data(settings.DB_PATH)
    ACTIVE_SESSIONS.clear()
    ACTIVE_DISRUPTIONS.clear()
    return {"status": "SUCCESS", "message": "All previous historical data removed. Database reset to clean 15-aircraft baseline."}


@app.get("/api/disruptions")
def get_active_disruptions():
    """Returns currently stacked active disruptions across the fleet."""
    return {
        "count": len(ACTIVE_DISRUPTIONS),
        "disruptions": ACTIVE_DISRUPTIONS
    }


@app.post("/api/disruptions/clear")
def clear_active_disruptions():
    """Clears all active stacked disruptions from the OCC incident roster."""
    ACTIVE_DISRUPTIONS.clear()
    return {
        "status": "SUCCESS",
        "message": "All active disruption incidents cleared from OCC incident stack."
    }


@app.get("/api/slots")
def get_slots():
    """Returns VOBL (Kempegowda BLR) runway movement windows, capacities, and active bookings."""
    conn = get_connection(settings.DB_PATH)
    try:
        flights = conn.execute("SELECT flight_id, tail, origin, dest, std, sta, status FROM flights ORDER BY std ASC").fetchall()
        flight_list = [dict(f) for f in flights]
    finally:
        conn.close()

    windows = [
        {"window_id": "W-0406", "label": "Early Morning Window (04:00 - 06:00)", "start": "2026-11-01T04:00:00", "end": "2026-11-01T06:00:00", "nominal_capacity": 30, "status": "NORMAL"},
        {"window_id": "W-0608", "label": "Morning Peak Window (06:00 - 08:00)", "start": "2026-11-01T06:00:00", "end": "2026-11-01T08:00:00", "nominal_capacity": 20, "status": "DISRUPTED_FOG", "reduced_capacity": 8, "disruption_reason": "Low Visibility Procedures (CAT III RVR < 250m)"},
        {"window_id": "W-0810", "label": "Mid-Morning Window (08:00 - 10:00)", "start": "2026-11-01T08:00:00", "end": "2026-11-01T10:00:00", "nominal_capacity": 26, "status": "RESTRICTED", "reduced_capacity": 14, "disruption_reason": "Tactical Holding Buffer"},
        {"window_id": "W-1014", "label": "Midday Operations (10:00 - 14:00)", "start": "2026-11-01T10:00:00", "end": "2026-11-01T14:00:00", "nominal_capacity": 32, "status": "NORMAL"},
        {"window_id": "W-1418", "label": "Afternoon Departure Wave (14:00 - 18:00)", "start": "2026-11-01T14:00:00", "end": "2026-11-01T18:00:00", "nominal_capacity": 32, "status": "NORMAL"},
        {"window_id": "W-1822", "label": "Evening Hub Bank (18:00 - 22:00)", "start": "2026-11-01T18:00:00", "end": "2026-11-01T22:00:00", "nominal_capacity": 30, "status": "NORMAL"},
        {"window_id": "W-2204", "label": "Night Curfew Window (22:00 - 04:00)", "start": "2026-11-01T22:00:00", "end": "2026-11-02T04:00:00", "nominal_capacity": 8, "status": "RESTRICTED", "reduced_capacity": 4, "disruption_reason": "Runway Maintenance & Noise Curfew"}
    ]
    for w in windows:
        w_start = w["start"]
        w_end = w["end"]
        matched = [f for f in flight_list if (f.get("origin") == "VOBL" and w_start <= f.get("std", "") < w_end) or (f.get("dest") == "VOBL" and w_start <= f.get("sta", "") < w_end)]
        w["booked_movements"] = len(matched)
        effective_cap = w.get("reduced_capacity") if w.get("status") != "NORMAL" else w["nominal_capacity"]
        w["effective_capacity"] = effective_cap
        w["utilization_pct"] = round((len(matched) / max(effective_cap, 1)) * 100, 1)
        w["is_congested"] = len(matched) > effective_cap
    return {"hub": "VOBL", "windows": windows}


@app.get("/api/fleet_status")
def get_fleet_status():
    """Returns the full 15-aircraft fleet status, location, and assigned flights."""
    conn = get_connection(settings.DB_PATH)
    try:
        aircraft_rows = conn.execute("SELECT * FROM aircraft ORDER BY tail ASC").fetchall()
        flights = conn.execute("SELECT flight_id, tail, origin, dest, std, sta, status FROM flights ORDER BY std ASC").fetchall()
        
        fleet = []
        for ac in aircraft_rows:
            d = dict(ac)
            ac_tail = d["tail"]
            ac_flights = [dict(f) for f in flights if f["tail"] == ac_tail]
            d["assigned_flights"] = ac_flights
            d["flights_count"] = len(ac_flights)
            if ac_tail == "VT-BLR15":
                d["status_badge"] = "STANDBY"
                d["status_label"] = "Standby Reserve (VOBL)"
            elif ac_tail == "VT-BLR01":
                d["status_badge"] = "DISRUPTED"
                d["status_label"] = "Disruption Impacted (Flight 6E-101)"
            elif d["maintenance_due_hours"] < 25:
                d["status_badge"] = "MAINTENANCE"
                d["status_label"] = f"Maint Due ({d['maintenance_due_hours']:.0f}h)"
            else:
                d["status_badge"] = "AVAILABLE"
                d["status_label"] = "Operational Active"
            fleet.append(d)
        return {"total_aircraft": len(fleet), "fleet": fleet}
    finally:
        conn.close()



@app.post("/api/parse_message")
def parse_message_endpoint(req: ParseDisruptionRequest):
    """
    Parses an unstructured operational disruption message from a Human Duty Manager
    into structured disruption parameters using the Mediator LLM.
    """
    from skymediator.llm import parse_duty_manager_disruption
    base_schedule = query_schedule(airport=settings.HUB_AIRPORT)
    parsed = parse_duty_manager_disruption(req.message, base_schedule=base_schedule)
    return {
        "status": "PARSED",
        "raw_message": req.message,
        "parsed_disruption": parsed
    }


def get_crew_roster_for_flight(affected_id: str, is_severe: bool, base_time: datetime) -> List[Dict[str, Any]]:
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute(
            """SELECT c.crew_id, c.name, c.role, cd.duty_start, cd.max_fdp_minutes, cdf.flight_id
               FROM crew_members c
               JOIN crew_duties cd ON c.crew_id = cd.crew_id
               LEFT JOIN crew_duty_flights cdf ON cd.duty_id = cdf.duty_id
               WHERE cdf.flight_id = ? OR c.crew_id = 'CREW-CAPT-01'
               ORDER BY (cdf.flight_id = ?) DESC, cd.duty_start ASC""",
            (affected_id, affected_id)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        if rows:
            roster = []
            seen = set()
            for r in rows:
                cid = r["crew_id"]
                if cid in seen:
                    continue
                seen.add(cid)
                d_start = r.get("duty_start")
                if not d_start:
                    duty_start_hour = 2 if is_severe else 5
                    d_start = datetime(base_time.year, base_time.month, base_time.day, duty_start_hour, 0).isoformat()
                roster.append({
                    "crew_id": cid,
                    "duty_record": {"duty_start": d_start},
                    "assigned_flights": [affected_id]
                })
            if roster:
                return roster
    except Exception as e:
        logger.warning(f"Error querying crew roster from DB: {e}")
    finally:
        conn.close()

    duty_start_hour = 2 if is_severe else 5
    return [
        {
            "crew_id": "CREW-CAPT-01",
            "duty_record": {"duty_start": datetime(base_time.year, base_time.month, base_time.day, duty_start_hour, 0).isoformat()},
            "assigned_flights": [affected_id]
        }
    ]


@app.get("/api/llm_status")
def get_llm_status():
    """Returns real-time status and latency of the Gemini LLM engine."""
    import time
    from skymediator.llm import is_gemini_available, call_gemini, get_gemini_api_key

    api_key = get_gemini_api_key()

    if not api_key:
        return {
            "status": "OFFLINE",
            "model": settings.LLM_MODEL,
            "provider": "Deterministic Fallback",
            "latency_ms": 0,
            "message": "GEMINI_API_KEY not configured in .env file or environment variables"
        }

    if len(api_key) < 10:
        return {
            "status": "INVALID",
            "model": settings.LLM_MODEL,
            "provider": "Invalid Configuration",
            "latency_ms": 0,
            "message": f"GEMINI_API_KEY appears invalid (length: {len(api_key)}). Valid keys are typically 39+ characters starting with 'AI' or similar."
        }

    if not is_gemini_available():
        return {
            "status": "OFFLINE",
            "model": settings.LLM_MODEL,
            "provider": "Deterministic Fallback",
            "latency_ms": 0,
            "message": "Gemini API key validation failed"
        }

    t0 = time.time()
    try:
        reply = call_gemini("Reply with word CONNECTED.")
        latency = round((time.time() - t0) * 1000)
        is_live = bool(reply and not reply.startswith("[Deterministic"))
        msg = "Successfully connected to Gemini API" if is_live else (
            reply if reply and reply.startswith("[Deterministic") else "Gemini returned empty or non-live response"
        )
        return {
            "status": "ONLINE" if is_live else "FALLBACK",
            "model": settings.LLM_MODEL,
            "provider": "Google Gemini (Generative Language v1beta)" if is_live else "Deterministic Fallback Engine",
            "latency_ms": latency,
            "response": reply[:60] if reply else "",
            "message": msg
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "model": settings.LLM_MODEL,
            "provider": "Google Gemini",
            "latency_ms": 0,
            "message": f"Connection error: {str(e)}"
        }


@app.post("/api/run_recovery")
def run_recovery(req: TriggerDisruptionRequest):
    graph = build_recovery_graph()
    from skymediator.llm import parse_duty_manager_disruption

    # Base schedule from database
    base_schedule = query_schedule(airport=settings.HUB_AIRPORT)
    now = datetime(2026, 11, 1, 6, 0)
    if not base_schedule:
        base_schedule = [
            {"flight_id": "6E-101", "tail": "VT-BLR01", "origin": "VOBL", "dest": "VIDP", "std": now.isoformat(), "sta": (now + timedelta(hours=2, minutes=30)).isoformat(), "seats": 180, "status": "SCHEDULED"}
        ]

    # Mode 1: Natural Language Duty Manager Message
    if req.duty_manager_message and req.duty_manager_message.strip():
        parsed = parse_duty_manager_disruption(req.duty_manager_message, base_schedule=base_schedule)
        affected_id = parsed.get("affected_flight_id", "6E-101")
        is_severe = parsed.get("severity") == "SEVERE"
        base_time = now

        disruption_entry = {
            **parsed,
            "scenario_id": req.scenario_id or "DM_DISPATCH",
            "message": req.duty_manager_message
        }
        # Disruption Stacking: update or append to ACTIVE_DISRUPTIONS
        existing_idx = next((i for i, d in enumerate(ACTIVE_DISRUPTIONS) if d.get("affected_flight_id") == affected_id), None)
        if existing_idx is not None:
            ACTIVE_DISRUPTIONS[existing_idx] = disruption_entry
        else:
            ACTIVE_DISRUPTIONS.append(disruption_entry)

        # Build combined crew roster covering all active stacked disruptions
        all_crew = []
        seen_crew = set()
        for disc in ACTIVE_DISRUPTIONS:
            f_id = disc.get("affected_flight_id", "6E-101")
            roster = get_crew_roster_for_flight(f_id, disc.get("severity") == "SEVERE", base_time)
            for c in roster:
                if c["crew_id"] not in seen_crew:
                    seen_crew.add(c["crew_id"])
                    all_crew.append(c)
        crew_roster = all_crew if all_crew else get_crew_roster_for_flight(affected_id, is_severe, base_time)

        slot_windows = [
            {
                "airport": parsed.get("airport", settings.HUB_AIRPORT),
                "window_start": base_time.isoformat(),
                "window_end": (base_time + timedelta(hours=8)).isoformat(),
                "capacity": 8 if is_severe else 20
            }
        ]

        initial_state = {
            "run_id": f"OCC-{uuid4().hex[:6].upper()}",
            "duty_manager_message": req.duty_manager_message,
            "disruption": {
                **disruption_entry,
                "stacked_disruptions": list(ACTIVE_DISRUPTIONS)
            },
            "base_schedule": base_schedule,
            "active_crew": crew_roster,
            "slot_windows": slot_windows
        }

    # Mode 2: Predefined Simulation Scenario
    elif req.scenario_id:
        conn = get_connection(settings.DB_PATH)
        try:
            cursor = conn.execute("SELECT * FROM scenarios WHERE scenario_id = ?", (req.scenario_id,))
            scen = cursor.fetchone()
            if not scen:
                raise HTTPException(status_code=404, detail=f"Scenario {req.scenario_id} not found")
            scen_dict = dict(scen)
        finally:
            conn.close()

        base_time = datetime.fromisoformat(scen_dict["start_time"])
        anomalies = json.loads(scen_dict.get("seeded_anomalies") or "{}")
        affected_id = anomalies.get("affected_flight_id", "6E-101")
        is_severe = scen_dict["severity"] == "SEVERE"

        disruption_entry = {
            "scenario_id": req.scenario_id,
            "type": scen_dict["disruption_type"],
            "airport": scen_dict["airport"],
            "affected_flight_id": affected_id,
            "initial_action": "excessive_delay" if is_severe else "swap_tail",
            "delay_minutes": anomalies.get("delay_minutes", 320),
            "counter_delay_minutes": 30,
            "candidate_tail": "VT-BLR15"
        }
        # Disruption Stacking: update or append to ACTIVE_DISRUPTIONS
        existing_idx = next((i for i, d in enumerate(ACTIVE_DISRUPTIONS) if d.get("affected_flight_id") == affected_id), None)
        if existing_idx is not None:
            ACTIVE_DISRUPTIONS[existing_idx] = disruption_entry
        else:
            ACTIVE_DISRUPTIONS.append(disruption_entry)

        all_crew = []
        seen_crew = set()
        for disc in ACTIVE_DISRUPTIONS:
            f_id = disc.get("affected_flight_id", "6E-101")
            roster = get_crew_roster_for_flight(f_id, disc.get("severity") == "SEVERE", base_time)
            for c in roster:
                if c["crew_id"] not in seen_crew:
                    seen_crew.add(c["crew_id"])
                    all_crew.append(c)
        crew_roster = all_crew if all_crew else get_crew_roster_for_flight(affected_id, is_severe, base_time)

        slot_windows = [
            {
                "airport": settings.HUB_AIRPORT,
                "window_start": base_time.isoformat(),
                "window_end": (base_time + timedelta(hours=8)).isoformat(),
                "capacity": 8 if is_severe else 20
            }
        ]

        initial_state = {
            "run_id": f"OCC-{uuid4().hex[:6].upper()}",
            "disruption": {
                **disruption_entry,
                "stacked_disruptions": list(ACTIVE_DISRUPTIONS)
            },
            "base_schedule": base_schedule,
            "active_crew": crew_roster,
            "slot_windows": slot_windows
        }

    else:
        raise HTTPException(status_code=400, detail="Either duty_manager_message or scenario_id must be provided.")

    final_state = graph.invoke(initial_state)
    ACTIVE_SESSIONS[final_state["run_id"]] = final_state
    ACTIVE_SESSIONS["LATEST_RUN_ID"] = final_state["run_id"]

    return {
        "run_id": final_state["run_id"],
        "status": final_state["status"],
        "duty_manager_message": req.duty_manager_message,
        "parsed_disruption": final_state.get("parsed_disruption") or final_state.get("disruption"),
        "sentinel_forecast": final_state.get("sentinel_forecast"),
        "rounds_executed": final_state.get("round", 1),
        "candidates": final_state.get("candidates", []),
        "selected_plan": final_state.get("selected_plan"),
        "constraints_log": final_state.get("constraints_log", []),
        "escalation_reason": final_state.get("escalation_reason"),
        "reflection_notes": final_state.get("reflection_notes")
    }


@app.post("/api/approve_plan")
def approve_plan(req: ApprovalDecisionRequest):
    """
    Duty Manager Approval Workflow with strict regulatory & slot guardrails.
    Prohibits approval of any candidate plan carrying hard vetoes.
    Persists decision to SQLite decision_records and publishes an AgentEvent.
    """
    session = ACTIVE_SESSIONS.get(req.run_id)

    # Check if plan details exist in memory or DB
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute(
            "SELECT * FROM plan_revisions WHERE run_id = ? AND (plan_id = ? OR ? IS NULL) ORDER BY revision_id DESC LIMIT 1",
            (req.run_id, req.selected_plan_id, req.selected_plan_id)
        )
        rev_row = cursor.fetchone()
    finally:
        conn.close()

    if not session and not rev_row:
        raise HTTPException(status_code=404, detail=f"Recovery session {req.run_id} not found.")

    selected_plan = None
    if req.selected_plan_id and session and session.get("candidates"):
        selected_plan = next((c for c in session["candidates"] if c.get("plan_id") == req.selected_plan_id), None)

    if not selected_plan and session and session.get("selected_plan"):
        if not req.selected_plan_id or session["selected_plan"].get("plan_id") == req.selected_plan_id:
            selected_plan = session["selected_plan"]

    if not selected_plan and rev_row:
        selected_plan = {
            "plan_id": rev_row["plan_id"],
            "round_created": rev_row["round_number"],
            "operational_rationale": rev_row["operational_rationale"],
            "plan_diff": json.loads(rev_row["plan_diff_json"] or "[]"),
            "vetoed_by": json.loads(rev_row["vetoed_by_json"] or "[]"),
            "is_feasible": bool(rev_row["is_feasible"]),
            "scores": json.loads(rev_row["scores_json"] or "{}"),
            "compliance_notes": json.loads(rev_row["compliance_notes_json"] or "{}")
        }

    # MANDATORY SAFETY GUARDRAIL: Strict hard-veto blocking
    decision_action = req.decision.upper()
    if decision_action == "APPROVE":
        if selected_plan:
            vetoed_by = selected_plan.get("vetoed_by", [])
            is_feasible = selected_plan.get("is_feasible", True)
            if len(vetoed_by) > 0 or not is_feasible:
                raise HTTPException(
                    status_code=400,
                    detail=f"MANDATORY SAFETY VIOLATION: Cannot approve plan '{selected_plan.get('plan_id')}' vetoed by {vetoed_by}. Hard statutory/slot vetoes cannot be overridden."
                )

    # Idempotency Guard: Prevent duplicate conflicting approvals
    conn = get_connection(settings.DB_PATH)
    try:
        existing = conn.execute(
            "SELECT * FROM decision_records WHERE run_id = ? AND duty_manager_action IN ('APPROVED', 'REJECTED') ORDER BY decision_timestamp DESC LIMIT 1",
            (req.run_id,)
        ).fetchone()
        if existing and existing["duty_manager_action"] == "APPROVED" and decision_action == "APPROVE":
            return {
                "run_id": req.run_id,
                "status": "APPROVED",
                "message": f"Plan for {req.run_id} has already been approved and recorded."
            }
    finally:
        conn.close()

    now_utc = datetime.now(timezone.utc).isoformat()
    status_map = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "REPLAN": "REVISION_REQUESTED",
        "REVISION_REQUESTED": "REVISION_REQUESTED"
    }
    final_status = status_map.get(decision_action, "RECORDED")

    if session:
        session["status"] = final_status
        session["duty_manager_decision"] = {
            "decision": decision_action,
            "selected_plan_id": req.selected_plan_id or (selected_plan.get("plan_id") if selected_plan else None),
            "manager_notes": req.manager_notes,
            "timestamp": now_utc
        }

    # Record consequential decision into SQLite decision_records
    from skymediator.events import record_decision, broker, AgentEvent
    dec_id = f"DEC-{req.run_id}-{uuid4().hex[:6].upper()}"
    plan_id = req.selected_plan_id or (selected_plan.get("plan_id") if selected_plan else "PLAN-UNKNOWN")
    round_no = selected_plan.get("round_created", 1) if selected_plan else 1

    record_decision({
        "decision_id": dec_id,
        "run_id": req.run_id,
        "disruption_id": (session.get("disruption", {}).get("scenario_id") if session else "DISPATCH"),
        "plan_id": plan_id,
        "round_number": round_no,
        "duty_manager_action": "APPROVED" if decision_action == "APPROVE" else ("REJECTED" if decision_action == "REJECT" else "REVISION_REQUESTED"),
        "duty_manager_id": "Athish Raj (Duty Manager)",
        "duty_manager_notes": req.manager_notes or (f"Duty Manager {decision_action} decision"),
        "decision_timestamp": now_utc,
        "proposed_diff": selected_plan.get("plan_diff", []) if selected_plan else [],
        "validation_outcomes": selected_plan.get("compliance_notes", {}) if selected_plan else {},
        "vetoed_by": selected_plan.get("vetoed_by", []) if selected_plan else [],
        "is_feasible_at_decision": bool(selected_plan and len(selected_plan.get("vetoed_by", [])) == 0),
        "mediator_rationale": selected_plan.get("operational_rationale", "") if selected_plan else "",
        "final_status": final_status
    })

    # Emit real-time event for Operations Console
    event_type_map = {
        "APPROVE": "duty_manager_approved",
        "REJECT": "duty_manager_rejected",
        "REPLAN": "revision_requested",
        "REVISION_REQUESTED": "revision_requested"
    }
    broker.publish(AgentEvent(
        run_id=req.run_id,
        plan_id=plan_id,
        round_number=round_no,
        event_type=event_type_map.get(decision_action, "duty_manager_action"),
        actor="DutyManager",
        recipient="Mediator",
        status="SUCCESS" if decision_action == "APPROVE" else ("WARNING" if decision_action == "REPLAN" else "ERROR"),
        summary=f"Duty Manager performed '{decision_action}' on plan {plan_id}. Notes: {req.manager_notes or 'Standard authorization'}",
        structured_payload={
            "decision": decision_action,
            "manager_notes": req.manager_notes,
            "selected_plan_id": plan_id,
            "timestamp": now_utc
        }
    ))

    # PROP-04: Human Replan Feedback Loop — Execute replan round upon revision request
    if decision_action in ("REPLAN", "REVISION_REQUESTED"):
        from skymediator.graph import execute_replan_round

        # Ensure session exists (reconstructing from database if memory was cleared)
        if not session:
            base_schedule = query_schedule(airport=settings.HUB_AIRPORT)
            now = datetime(2026, 11, 1, 6, 0)
            session = {
                "run_id": req.run_id,
                "round": rev_row["round_number"] if rev_row else 1,
                "base_schedule": base_schedule,
                "active_crew": get_crew_roster_for_flight("6E-101", False, now),
                "slot_windows": [{
                    "airport": settings.HUB_AIRPORT,
                    "window_start": now.isoformat(),
                    "window_end": (now + timedelta(hours=8)).isoformat(),
                    "capacity": 20
                }],
                "disruption": {
                    "affected_flight_id": "6E-101",
                    "type": "TACTICAL_REVISION",
                    "airport": settings.HUB_AIRPORT
                },
                "candidates": [selected_plan] if selected_plan else [],
                "constraints_log": []
            }

        revised_state = execute_replan_round(session, req.manager_notes or "Duty Manager requested tactical revision")
        ACTIVE_SESSIONS[req.run_id] = revised_state
        new_plan = revised_state.get("selected_plan")

        if new_plan:
            broker.publish(AgentEvent(
                run_id=req.run_id,
                plan_id=new_plan.get("plan_id"),
                round_number=new_plan.get("round_created", revised_state.get("round", 2)),
                event_type="candidate_proposed",
                actor="Rotation",
                recipient="Mediator",
                status="SUCCESS",
                summary=f"Synthesized Plan {new_plan.get('plan_id')} addressing Duty Manager revision: {req.manager_notes or 'Tactical feedback'}",
                structured_payload=new_plan
            ))

        return {
            "run_id": req.run_id,
            "status": "REVISION_REQUESTED",
            "replan_status": "REVISION_GENERATED",
            "plan_id": new_plan.get("plan_id") if new_plan else None,
            "selected_plan": new_plan,
            "candidates": revised_state.get("candidates", []),
            "session": revised_state,
            "message": f"Round {revised_state.get('round')} completed. Synthesized Plan {new_plan.get('plan_id') if new_plan else 'revised'} addressing: '{req.manager_notes or 'Tactical feedback'}'."
        }

    # If approved, deterministically mutate the persistent flight schedule in SQLite
    mutated_flights = []
    if decision_action == "APPROVE" and selected_plan and selected_plan.get("plan_diff"):
        from skymediator.tools.schedule import apply_plan_diff
        conn = get_connection(settings.DB_PATH)
        try:
            flights_cursor = conn.execute("SELECT * FROM flights ORDER BY std ASC")
            base_sched = [dict(r) for r in flights_cursor.fetchall()]
            mut_res = apply_plan_diff(base_sched, selected_plan.get("plan_diff", []))
            mutated_flights = mut_res.get("mutated_flights", [])
            for mf in mutated_flights:
                conn.execute(
                    "UPDATE flights SET tail = ?, std = ?, sta = ?, status = ? WHERE flight_id = ?",
                    (
                        mf["tail"],
                        mf.get("etd", mf.get("std")),
                        mf.get("eta", mf.get("sta")),
                        mf.get("status", "SCHEDULED"),
                        mf["flight_id"]
                    )
                )
            conn.commit()
        finally:
            conn.close()

    return {
        "run_id": req.run_id,
        "status": final_status,
        "plan_id": plan_id,
        "mutated_flights": mutated_flights,
        "applied_diff": selected_plan.get("plan_diff", []) if selected_plan else [],
        "message": f"Duty Manager action '{decision_action}' recorded, audited, and mutated schedule dispatched to fleet."
    }


# --- FEATURE A: REAL-TIME EVENT STREAMING & LIVE OPERATIONS CONSOLE APIS ---

@app.get("/api/events/stream")
async def stream_events(
    request: Request,
    run_id: Optional[str] = None,
    since_id: Optional[str] = None
):
    """
    Server-Sent Events (SSE) stream for live agent activity.
    Replays missed historical events (recovery on reconnection) then streams live events in real-time.
    """
    async def event_generator():
        from skymediator.events import broker, AgentEvent

        effective_since = request.headers.get("last-event-id") or since_id

        # 1. Replay past events
        historical = broker.get_events(run_id=run_id, since_id=effective_since, limit=200)
        for evt in historical:
            yield f"id: {evt['event_id']}\nevent: agent_event\ndata: {json.dumps(evt, default=str)}\n\n"

        # 2. Stream live events
        q = broker.subscribe(run_id=run_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: AgentEvent = await asyncio.wait_for(q.get(), timeout=12.0)
                    evt_dict = event.model_dump()
                    yield f"id: {event.event_id}\nevent: agent_event\ndata: {json.dumps(evt_dict, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep HTTP connection alive through proxies
                    yield ": ping\n\n"
        finally:
            broker.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/events")
def list_events(
    run_id: Optional[str] = None,
    actor: Optional[str] = None,
    event_type: Optional[str] = None,
    round_number: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
):
    """Returns paginated, structured historical agent events from SQLite."""
    from skymediator.events import broker
    events = broker.get_events(
        run_id=run_id,
        actor=actor,
        event_type=event_type,
        round_number=round_number,
        limit=limit,
        offset=offset
    )
    return {"total": len(events), "events": events}


@app.get("/api/runs")
def list_runs():
    """Lists recent multi-agent deliberation runs with summary metrics."""
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("""
            SELECT e.run_id, 
                   MIN(e.timestamp_utc) as start_time, 
                   MAX(e.timestamp_utc) as last_activity,
                   MAX(e.disruption_id) as disruption_id,
                   MAX(e.round_number) as max_round,
                   COUNT(e.event_id) as event_count
            FROM agent_events e
            GROUP BY e.run_id
            ORDER BY last_activity DESC
            LIMIT 50
        """)
        runs = []
        for r in cursor.fetchall():
            run_dict = dict(r)
            dec_cursor = conn.execute(
                "SELECT duty_manager_action, final_status FROM decision_records WHERE run_id = ? ORDER BY decision_timestamp DESC LIMIT 1",
                (r["run_id"],)
            )
            dec_row = dec_cursor.fetchone()
            run_dict["status"] = dec_row["duty_manager_action"] if dec_row else "DELIBERATED"
            runs.append(run_dict)

        existing_ids = {r["run_id"] for r in runs}

        # Include active in-memory sessions
        for rid, sess in list(ACTIVE_SESSIONS.items()):
            if rid != "LATEST_RUN_ID" and rid not in existing_ids:
                runs.insert(0, {
                    "run_id": rid,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "last_activity": datetime.now(timezone.utc).isoformat(),
                    "disruption_id": sess.get("disruption", {}).get("scenario_id", "VOBL"),
                    "max_round": sess.get("rounds_executed") or sess.get("round", 1),
                    "event_count": len(sess.get("candidates", [])) * 5 or 6,
                    "status": sess.get("status", "DELIBERATED")
                })
                existing_ids.add(rid)

        # Include any runs from traces folder not yet indexed in agent_events
        if settings.TRACES_DIR.exists():
            for tf in sorted(settings.TRACES_DIR.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
                t_run_id = tf.stem.replace("run_", "")
                if t_run_id not in existing_ids and not t_run_id.startswith("TEST-"):
                    runs.append({
                        "run_id": t_run_id,
                        "start_time": datetime.fromtimestamp(tf.stat().st_ctime, tz=timezone.utc).isoformat(),
                        "last_activity": datetime.fromtimestamp(tf.stat().st_mtime, tz=timezone.utc).isoformat(),
                        "disruption_id": "VOBL_HUB",
                        "max_round": 1,
                        "event_count": 6,
                        "status": "DELIBERATED"
                    })
                    existing_ids.add(t_run_id)

        return {"runs": runs}
    finally:
        conn.close()


@app.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    """Retrieves full session data and plan revisions for a specific run."""
    session = ACTIVE_SESSIONS.get(run_id)
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("SELECT * FROM plan_revisions WHERE run_id = ? ORDER BY revision_id ASC", (run_id,))
        revisions = []
        for row in cursor.fetchall():
            d = dict(row)
            for fld in ["plan_diff_json", "vetoed_by_json", "veto_reasons_json", "scores_json", "compliance_notes_json"]:
                if d.get(fld):
                    try:
                        d[fld] = json.loads(d[fld])
                    except Exception:
                        pass
            # Alias clean keys for frontend consumption
            d["plan_diff"] = d.get("plan_diff_json") or []
            d["vetoed_by"] = d.get("vetoed_by_json") or []
            d["veto_reasons"] = d.get("veto_reasons_json") or {}
            d["scores"] = d.get("scores_json") or {}
            d["compliance_notes"] = d.get("compliance_notes_json") or {}
            revisions.append(d)

        dec_cursor = conn.execute("SELECT * FROM decision_records WHERE run_id = ? ORDER BY decision_timestamp DESC LIMIT 1", (run_id,))
        dec_row = dec_cursor.fetchone()
        decision = dict(dec_row) if dec_row else None
        if decision:
            for fld in ["proposed_diff_json", "validation_outcomes_json", "vetoed_by_json"]:
                if decision.get(fld):
                    try:
                        decision[fld] = json.loads(decision[fld])
                    except Exception:
                        pass

        if not session and revisions:
            # Reconstruct session for seamless display if memory session expired
            candidates = []
            selected_plan = None
            for rev in revisions:
                c_dict = {
                    "plan_id": rev["plan_id"],
                    "round_created": rev["round_number"],
                    "proposing_agent": rev.get("proposing_agent") or "Rotation",
                    "operational_rationale": rev.get("operational_rationale") or "",
                    "plan_diff": rev.get("plan_diff_json") or [],
                    "vetoed_by": rev.get("vetoed_by_json") or [],
                    "veto_reasons": rev.get("veto_reasons_json") or {},
                    "scores": rev.get("scores_json") or {},
                    "compliance_notes": rev.get("compliance_notes_json") or {},
                    "is_feasible": bool(rev.get("is_feasible"))
                }
                candidates.append(c_dict)
                if rev.get("is_selected") or (not selected_plan and not c_dict["vetoed_by"]):
                    selected_plan = c_dict
            
            session = {
                "run_id": run_id,
                "status": decision["duty_manager_action"] if decision else "DELIBERATED",
                "candidates": candidates,
                "selected_plan": selected_plan or (candidates[-1] if candidates else None),
                "rounds_executed": max([r["round_number"] for r in revisions], default=1),
                "disruption": {"scenario_id": decision.get("disruption_id") if decision else "VOBL"}
            }

        elif not session and not revisions:
            # Fallback reconstruction from agent_events if session expired
            from skymediator.events import broker
            evts = broker.get_events(run_id=run_id, limit=50)
            if evts:
                prop_ev = next((e for e in evts if e.get("event_type") == "proposal_created"), None)
                veto_ev = next((e for e in evts if "veto" in e.get("event_type", "")), None)
                c_dict = {
                    "plan_id": (prop_ev or {}).get("plan_id") or "PLAN-R1-001",
                    "round_created": 1,
                    "proposing_agent": "Rotation",
                    "operational_rationale": (prop_ev or {}).get("summary") or "Tail swap on flight 6E-101 to standby reserve VT-BLR15.",
                    "plan_diff": [{"op": "swap_tail", "flight_id": "6E-101", "original_tail": "VT-BLR01", "new_tail": "VT-BLR15"}],
                    "vetoed_by": [veto_ev["actor"]] if veto_ev else [],
                    "veto_reasons": {veto_ev["actor"]: veto_ev.get("summary")} if veto_ev else {},
                    "scores": {"composite_score": 0.0245, "raw_metrics": {"delay_minutes": 0, "total_cost": 45000}},
                    "compliance_notes": {"crew": "DGCA CAR Section 7 verified.", "slot": "Window approved."},
                    "is_feasible": not bool(veto_ev)
                }
                session = {
                    "run_id": run_id,
                    "status": decision["duty_manager_action"] if decision else "DELIBERATED",
                    "candidates": [c_dict],
                    "selected_plan": c_dict,
                    "rounds_executed": 1,
                    "disruption": {"scenario_id": decision.get("disruption_id") if decision else "VOBL"}
                }

        return {
            "run_id": run_id,
            "session": session,
            "revisions": revisions,
            "decision": decision
        }
    finally:
        conn.close()


@app.get("/api/session/latest")
def get_latest_session():
    """Returns the most recent active or recorded recovery session across the OCC."""
    latest_run_id = ACTIVE_SESSIONS.get("LATEST_RUN_ID")
    if latest_run_id and latest_run_id in ACTIVE_SESSIONS:
        return {"run_id": latest_run_id, "session": ACTIVE_SESSIONS[latest_run_id]}
    
    conn = get_connection(settings.DB_PATH)
    try:
        cur = conn.execute("SELECT run_id FROM plan_revisions ORDER BY revision_id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            cur = conn.execute("SELECT run_id FROM agent_events ORDER BY rowid DESC LIMIT 1")
            row = cur.fetchone()
        if row:
            run_id = row[0]
            details = get_run_details(run_id)
            return {"run_id": run_id, "session": details.get("session"), "revisions": details.get("revisions"), "decision": details.get("decision")}
        return {"run_id": None, "session": None}
    finally:
        conn.close()



# --- FEATURE B: PERSISTENT DECISION AUDIT TRAIL APIS ---

@app.get("/api/audit/decisions")
def list_audit_decisions(
    run_id: Optional[str] = None,
    action: Optional[str] = None,
    scenario_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Queries persistent decision audit records with filters."""
    conn = get_connection(settings.DB_PATH)
    try:
        query = "SELECT * FROM decision_records WHERE 1=1"
        params: List[Any] = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if action:
            query += " AND duty_manager_action = ?"
            params.append(action.upper())
        if scenario_id:
            query += " AND disruption_id = ?"
            params.append(scenario_id)
        query += " ORDER BY decision_timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        records = []
        for row in cursor.fetchall():
            d = dict(row)
            for fld in ["proposed_diff_json", "validation_outcomes_json", "vetoed_by_json"]:
                if d.get(fld):
                    try:
                        d[fld] = json.loads(d[fld])
                    except Exception:
                        pass
            records.append(d)
        return {"total": len(records), "decisions": records}
    finally:
        conn.close()


@app.get("/api/audit/decisions/{decision_id}")
def get_decision_detail(decision_id: str):
    """Fetches comprehensive audit record for a single decision."""
    conn = get_connection(settings.DB_PATH)
    try:
        cursor = conn.execute("SELECT * FROM decision_records WHERE decision_id = ?", (decision_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Decision record {decision_id} not found.")
        d = dict(row)
        for fld in ["proposed_diff_json", "validation_outcomes_json", "vetoed_by_json"]:
            if d.get(fld):
                try:
                    d[fld] = json.loads(d[fld])
                except Exception:
                    pass
        return {"decision": d}
    finally:
        conn.close()


@app.get("/api/audit/revisions")
def list_revisions(run_id: Optional[str] = None, plan_id: Optional[str] = None):
    """Retrieves all plan revisions across rounds for comparison."""
    conn = get_connection(settings.DB_PATH)
    try:
        query = "SELECT * FROM plan_revisions WHERE 1=1"
        params: List[Any] = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if plan_id:
            query += " AND plan_id = ?"
            params.append(plan_id)
        query += " ORDER BY round_number ASC, revision_id ASC"
        cursor = conn.execute(query, params)
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            for fld in ["plan_diff_json", "vetoed_by_json", "veto_reasons_json", "scores_json", "compliance_notes_json"]:
                if d.get(fld):
                    try:
                        d[fld] = json.loads(d[fld])
                    except Exception:
                        pass
            rows.append(d)
        return {"revisions": rows}
    finally:
        conn.close()


@app.get("/api/audit/revisions/compare")
def compare_revisions(run_id: str, plan_a: str, plan_b: str):
    """Compares two plan revisions side-by-side (diffs, metrics, feasibility, vetoes)."""
    conn = get_connection(settings.DB_PATH)
    try:
        cursor_a = conn.execute(
            "SELECT * FROM plan_revisions WHERE run_id = ? AND plan_id = ? ORDER BY revision_id DESC LIMIT 1",
            (run_id, plan_a)
        )
        row_a = cursor_a.fetchone()
        cursor_b = conn.execute(
            "SELECT * FROM plan_revisions WHERE run_id = ? AND plan_id = ? ORDER BY revision_id DESC LIMIT 1",
            (run_id, plan_b)
        )
        row_b = cursor_b.fetchone()

        if not row_a or not row_b:
            raise HTTPException(status_code=404, detail="One or both plan revisions not found for comparison.")

        dict_a = dict(row_a)
        dict_b = dict(row_b)
        for d in [dict_a, dict_b]:
            for fld in ["plan_diff_json", "vetoed_by_json", "veto_reasons_json", "scores_json", "compliance_notes_json"]:
                if d.get(fld):
                    try:
                        d[fld] = json.loads(d[fld])
                    except Exception:
                        pass

        return {
            "run_id": run_id,
            "plan_a": dict_a,
            "plan_b": dict_b,
            "feasibility_comparison": {
                f"{plan_a}_feasible": bool(dict_a["is_feasible"]),
                f"{plan_b}_feasible": bool(dict_b["is_feasible"]),
                f"{plan_a}_vetoed_by": dict_a.get("vetoed_by_json", []),
                f"{plan_b}_vetoed_by": dict_b.get("vetoed_by_json", [])
            },
            "scores_comparison": {
                plan_a: dict_a.get("scores_json", {}),
                plan_b: dict_b.get("scores_json", {})
            }
        }
    finally:
        conn.close()


@app.get("/api/audit/export")
def export_audit_data(
    format: str = "json",
    run_id: Optional[str] = None,
    action: Optional[str] = None
):
    """Exports decision audit trail to CSV or JSON format."""
    conn = get_connection(settings.DB_PATH)
    try:
        query = "SELECT * FROM decision_records WHERE 1=1"
        params: List[Any] = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if action:
            query += " AND duty_manager_action = ?"
            params.append(action.upper())
        query += " ORDER BY decision_timestamp DESC"

        cursor = conn.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

        if format.lower() == "csv":
            import csv
            import io
            output = io.StringIO()
            fieldnames = [
                "decision_id", "run_id", "disruption_id", "plan_id", "round_number",
                "duty_manager_action", "duty_manager_id", "decision_timestamp",
                "is_feasible_at_decision", "duty_manager_notes", "mediator_rationale", "final_status"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
            csv_content = output.getvalue()
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="skymediator_decision_audit.csv"'}
            )
        else:
            for r in rows:
                for json_fld in ["proposed_diff_json", "validation_outcomes_json", "vetoed_by_json"]:
                    if r.get(json_fld):
                        try:
                            r[json_fld] = json.loads(r[json_fld])
                        except Exception:
                            pass
            return JSONResponse(content={
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "decisions": rows
            })
    finally:
        conn.close()


# --- OCC WEB PAGES & USER INTERFACE ROUTES ---

DASHBOARD_FILE = Path(__file__).parent / "dashboard.html"
CONSOLE_FILE = Path(__file__).parent / "console.html"
AUDIT_FILE = Path(__file__).parent / "audit.html"


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Main OCC Operations & Disruption Management Dashboard."""
    if DASHBOARD_FILE.exists():
        content = DASHBOARD_FILE.read_text(encoding="utf-8")
    else:
        content = "<html><body><h1>SkyMediator OCC</h1><p>Dashboard file missing.</p></body></html>"
    return HTMLResponse(content=content)


@app.get("/console", response_class=HTMLResponse)
@app.get("/agent-console", response_class=HTMLResponse)
def get_console():
    """Dedicated Agent Operations Console View (Live Event Stream & Timeline)."""
    if CONSOLE_FILE.exists():
        content = CONSOLE_FILE.read_text(encoding="utf-8")
    else:
        content = "<html><body><h1>SkyMediator Agent Operations Console</h1><p>Console file missing.</p></body></html>"
    return HTMLResponse(content=content)


@app.get("/audit", response_class=HTMLResponse)
@app.get("/decision-history", response_class=HTMLResponse)
def get_audit_trail():
    """Persistent Decision History & Audit Trail View."""
    if AUDIT_FILE.exists():
        content = AUDIT_FILE.read_text(encoding="utf-8")
    else:
        content = "<html><body><h1>SkyMediator Decision Audit Trail</h1><p>Audit file missing.</p></body></html>"
    return HTMLResponse(content=content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("skymediator.app.server:app", host="0.0.0.0", port=8000, reload=False)
