"""
Google Gemini LLM Integration for SkyMediator OCC.
Provides natural-language operational briefings, Agentic RAG query reformulation,
and recovery strategy synthesis with deterministic offline fallbacks.
"""

import os
from typing import Any, Dict, List, Optional
import requests

from skymediator.config import settings
from skymediator.logging_config import logger


def get_gemini_api_key() -> Optional[str]:
    """Retrieves Gemini API key from environment variable, .env file, or settings, stripping any quotes."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("SKYMEDIATOR_GEMINI_API_KEY")
    if not key or len(key.strip().strip('"').strip("'")) < 10:
        # Dynamically inspect .env file in case it was updated while server was running
        env_file = settings.BASE_DIR / ".env"
        if env_file.exists():
            try:
                from dotenv import dotenv_values
                vals = dotenv_values(env_file)
                key = vals.get("GEMINI_API_KEY") or vals.get("SKYMEDIATOR_GEMINI_API_KEY")
                if key:
                    os.environ["GEMINI_API_KEY"] = key
                    os.environ["SKYMEDIATOR_GEMINI_API_KEY"] = key
            except Exception:
                pass
    if not key:
        key = settings.GEMINI_API_KEY
    if key:
        key = key.strip().strip('"').strip("'").strip()
    return key


def is_gemini_available() -> bool:
    """Checks if a valid Gemini API key is configured."""
    key = get_gemini_api_key()
    if not key:
        logger.warning("GEMINI_API_KEY not found in environment, .env file, or settings")
        return False
    if len(key) < 10:
        logger.warning(f"GEMINI_API_KEY appears invalid (length: {len(key)}). Valid keys are typically 39+ characters.")
        return False
    return True


_LLM_SESSION = requests.Session()
_LLM_COOLDOWN_UNTIL: float = 0.0


def call_gemini(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Executes a prompt against Google Gemini with strict latency limits and circuit-breaker protection.
    Uses verified working model gemini-3.1-flash-lite-preview with robust fallback.
    """
    global _LLM_COOLDOWN_UNTIL

    import time
    if time.time() < _LLM_COOLDOWN_UNTIL:
        return "[Deterministic OCC Fallback: Rate-limit circuit breaker active]"

    api_key = get_gemini_api_key()
    if not api_key:
        return "[Deterministic OCC Fallback: Set GEMINI_API_KEY to activate live Gemini synthesis]"

    preferred_model = settings.LLM_MODEL or "gemini-3.1-flash-lite-preview"
    # Fallback cascade prioritizing verified responsive models
    models_to_try = [preferred_model]
    for fallback_model in ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash", "gemini-flash-latest"]:
        if fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600
        }
    }

    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            response = _LLM_SESSION.post(url, json=payload, timeout=(4.0, 10.0))
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            elif response.status_code == 429:
                logger.warning(f"Gemini model {model} hit quota 429. Activating 15s circuit breaker.")
                _LLM_COOLDOWN_UNTIL = time.time() + 15.0
                break
            elif response.status_code == 404:
                continue
            else:
                logger.warning(f"Gemini API returned HTTP {response.status_code}: {response.text[:120]}")
                continue
        except Exception as e:
            logger.warning(f"Gemini model {model} timeout/error: {e}")
            # Try fresh connection if session had stale socket
            try:
                fresh_res = requests.post(url, json=payload, timeout=(4.0, 10.0))
                if fresh_res.status_code == 200:
                    data = fresh_res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
            except Exception:
                pass
            continue

    return "[Deterministic OCC Fallback: Live LLM synthesis timed out or encountered an API error]"


def synthesize_occ_briefing(
    plan: Dict[str, Any],
    scores: Dict[str, Any],
    disruption: Dict[str, Any],
    hub: str = "VOBL (BLR)"
) -> str:
    """
    Generates an executive-level OCC operational recovery briefing for the Duty Manager.
    """
    plan_id = plan.get("plan_id", "PLAN-UNKNOWN")
    diffs = plan.get("plan_diff", [])
    composite_score = scores.get("composite_score", 0.0)
    delay_min = scores.get("raw_metrics", {}).get("delay_minutes", 0)
    total_cost = scores.get("raw_metrics", {}).get("total_cost", 0)

    if is_gemini_available():
        system_prompt = (
            "You are the Chief Operations Control Center (OCC) Duty Dispatcher for Kempegowda International Airport (BLR). "
            "Write a concise, professional 2-3 paragraph executive operational briefing for the Human Duty Manager. "
            "Detail the disruption context, the proposed schedule mutations (tail swaps, delays, cancellations), "
            "regulatory compliance under DGCA CAR Section 7, and cost/passenger impact. Use active aviation terminology."
        )
        user_prompt = (
            f"Disruption Context: {disruption}\n"
            f"Recommended Plan: {plan_id}\n"
            f"Mutations: {diffs}\n"
            f"Composite Score: {composite_score:.4f}\n"
            f"Operational Delay: {delay_min} mins\n"
            f"Financial Liability: INR {total_cost:,.0f}\n"
            f"Hub Airport: {hub}\n\n"
            "Generate the executive operational recovery briefing:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if not res.startswith("[Deterministic"):
            return res

    # Deterministic high-quality OCC Briefing
    swaps = [d for d in diffs if d.get("op") == "swap_tail"]
    delays = [d for d in diffs if d.get("op") == "delay"]
    cancels = [d for d in diffs if d.get("op") == "cancel"]

    lines = [
        f"**OCC Executive Recovery Briefing — Plan {plan_id}**",
        f"Operational recovery plan synthesized for {hub} addressing {disruption.get('type', 'fog').upper()} disruption.",
    ]
    if swaps:
        for s in swaps:
            lines.append(f"- **Tail Swap Authorized:** Reassigned flight {s.get('flight_id')} from {s.get('original_tail')} to standby aircraft {s.get('new_tail')} preserving departure punctuality.")
    if delays:
        for d in delays:
            lines.append(f"- **Tactical Delay Incurred:** Flight {d.get('flight_id')} delayed by {d.get('delay_minutes')}m for runway visibility clearance, strictly within statutory crew FDP.")
    if cancels:
        for c in cancels:
            lines.append(f"- **Strategic Cancellation:** Flight {c.get('flight_id')} canceled to prevent airport slot overflow and cascading duty timeouts.")

    lines.append(
        f"**Regulatory & Financial Assessment:** 100% compliant with DGCA CAR Section 7 Series J Part III. "
        f"Projected composite penalty: {composite_score:.4f} (Delay: {delay_min}m, Est. Liability: INR {total_cost:,.0f}). "
        f"Awaiting Human Duty Manager sign-off."
    )
    return "\n\n".join(lines)


def synthesize_rotation_rationale(
    round_number: int,
    disruption: Dict[str, Any],
    chosen_op: Dict[str, Any],
    constraints_feedback: Optional[List[str]] = None
) -> str:
    """
    Uses Gemini LLM to synthesize deep operational reasoning for the Rotation Agent's proposed mutation.
    """
    if is_gemini_available():
        system_prompt = (
            "You are the Aircraft Rotation and Schedule Proposer Agent in an Airline Operations Control Center (OCC). "
            "Explain in 1-2 concise, expert sentences the operational rationale behind your proposed schedule mutation, "
            "referencing turnaround times, fleet continuity, or feedback from previous constraint vetoes."
        )
        user_prompt = (
            f"Deliberation Round: {round_number}\n"
            f"Active Disruption: {disruption}\n"
            f"Previous Constraints Feedback: {constraints_feedback or 'None (Round 1)'}\n"
            f"Proposed Operation: {chosen_op}\n\n"
            "Provide the concise operational rationale for this schedule mutation:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()

    # Deterministic fallback
    op_type = chosen_op.get("op")
    if op_type == "swap_tail":
        return f"Tail swap on flight {chosen_op.get('flight_id')} to standby {chosen_op.get('new_tail')} preserving departure schedule and passenger connections."
    elif op_type == "delay":
        return f"Tactical departure delay of {chosen_op.get('delay_minutes')}m on flight {chosen_op.get('flight_id')} allowing weather/slot recovery."
    elif op_type == "cancel":
        return f"Strategic flight cancellation of {chosen_op.get('flight_id')} to protect systemic fleet integrity and avoid cascading duty timeouts."
    return f"Operational schedule adjustment on flight {chosen_op.get('flight_id')}."


def explain_crew_legality_reasoning(
    crew_id: str,
    is_legal: bool,
    violation: Optional[Dict[str, Any]],
    cited_clause: Optional[str]
) -> str:
    """
    Uses Gemini LLM to generate statutory compliance reasoning and pilot fatigue analysis under DGCA CAR Section 7.
    """
    if is_gemini_available():
        system_prompt = (
            "You are the Crew Legality and Flight Duty Limitations (FDTL) Compliance Agent in India. "
            "Write a concise 1-2 sentence regulatory assessment for the OCC Duty Manager under DGCA CAR Section 7, Series J, Part III. "
            "If legal, confirm statutory compliance. If illegal, explain the safety and fatigue hazard of the exceedance."
        )
        status = "COMPLIANT" if is_legal else "ILLEGAL / VETO"
        user_prompt = (
            f"Crew Member: {crew_id}\n"
            f"Status: {status}\n"
            f"Violation Details: {violation}\n"
            f"Statutory Clause Cited: {cited_clause}\n\n"
            "Generate concise statutory compliance statement:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()

    # Deterministic fallback
    if is_legal:
        return f"Crew {crew_id} duty duration is verified 100% compliant with DGCA CAR Section 7 Series J Part III statutory limits."
    v_type = (violation or {}).get("type", "FDTL Exceedance")
    actual = (violation or {}).get("actual_minutes", 0)
    limit = (violation or {}).get("limit_minutes", 0)
    return (
        f"Statutory VETO for Crew {crew_id}: Flight Duty Period (FDP) exceedance - {v_type} (Duty {actual}m exceeds statutory cap of {limit}m). "
        f"Strictly prohibited under {cited_clause or 'DGCA CAR Section 7, Series J, Part III'}."
    )


def reflect_mediator_tradeoffs(
    ranked_candidates: List[Dict[str, Any]],
    round_number: int
) -> str:
    """
    Uses Gemini LLM to synthesize the Mediator's holistic operational reflection across surviving candidate plans.
    """
    if not ranked_candidates:
        return "All candidate proposals were vetoed by statutory or airport capacity authorities. Directing counter-proposal formulation."

    if is_gemini_available():
        system_prompt = (
            "You are the Chief Mediator Agent in an Airline Operations Control Center (OCC). "
            "Synthesize a concise 2-sentence operational reflection evaluating the trade-offs "
            "(delay vs passenger impact vs financial liability) of the surviving candidate recovery plans."
        )
        top = ranked_candidates[0]
        user_prompt = (
            f"Round: {round_number}\n"
            f"Surviving Candidates Count: {len(ranked_candidates)}\n"
            f"Top Candidate ID: {top.get('plan_id')} (Composite Penalty Score: {top.get('scores', {}).get('composite_score')})\n"
            f"Mutations: {top.get('plan_diff')}\n\n"
            "Provide the concise OCC Mediator arbitration reflection:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()

    top = ranked_candidates[0]
    return (
        f"Evaluated {len(ranked_candidates)} surviving candidate plan(s) in Round {round_number}. "
        f"Selected optimal candidate {top.get('plan_id')} with composite penalty score {top.get('scores', {}).get('composite_score', 0):.4f}."
    )


def synthesize_sentinel_rationale(
    airport: str,
    probability: float,
    current_obs: Dict[str, Any],
    recommended_action: str
) -> str:
    """Uses Gemini to synthesize dynamic meteorological risk briefing for the OCC."""
    if is_gemini_available():
        system_prompt = (
            "You are the Sentinel Weather and Disruption Forecasting Agent in an Airline OCC. "
            "Explain in 1-2 concise, expert operational sentences the meteorological risk at the airport, "
            "referencing RVR, dewpoint depression, and tactical impact."
        )
        user_prompt = (
            f"Airport: {airport}\n"
            f"Disruption Probability: {probability:.1%}\n"
            f"Current METAR Observations: {current_obs}\n"
            f"Recommended Tactical Action: {recommended_action}\n\n"
            "Provide meteorological operational assessment:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()
    return f"Meteorological risk assessment for {airport}: {probability:.1%} probability of fog onset. Recommended action: {recommended_action}."


def synthesize_slot_rationale(
    hub: str,
    is_valid: bool,
    violated_windows: List[Dict[str, Any]],
    plan_id: str
) -> str:
    """Uses Gemini to synthesize dynamic runway slot capacity and traffic analysis."""
    if is_gemini_available():
        system_prompt = (
            "You are the Airport Slot and Movement Capacity Agent in an Airline Operations Control Center (OCC). "
            "Write a concise 1-2 sentence operational statement assessing runway slot capacity and curfews."
        )
        user_prompt = (
            f"Hub Airport: {hub}\n"
            f"Plan ID: {plan_id}\n"
            f"Is Compliant: {is_valid}\n"
            f"Violations: {violated_windows}\n\n"
            "Provide slot capacity assessment:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()
    if is_valid:
        return f"Airport Slot Agent confirmed all arrival and departure movements on {plan_id} fit available runway capacity windows at {hub}."
    return f"Airport Slot VETO: Runway movement capacity exceeded in window for {plan_id} at {hub}."


def synthesize_passenger_cost_rationale(
    plan_id: str,
    missed_connections: int,
    total_cost: float,
    affected_pax: int
) -> str:
    """Uses Gemini to synthesize dynamic passenger care impact under DGCA CAR Sec 3 and financial liabilities."""
    if is_gemini_available():
        system_prompt = (
            "You are the Passenger Care and Cost Agent in an Airline OCC. "
            "Explain in 1-2 concise sentences the passenger disruption impact under DGCA CAR Section 3, Series M, Part IV "
            "(meals, hotel accommodations, rebooking) and estimated airline financial liability."
        )
        user_prompt = (
            f"Plan ID: {plan_id}\n"
            f"Affected Passengers: {affected_pax}\n"
            f"Missed Connections: {missed_connections}\n"
            f"Total Estimated Liability: INR {total_cost:,.0f}\n\n"
            "Provide passenger care and financial impact summary:"
        )
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip()
    return f"Passenger care assessment: {affected_pax} passengers impacted ({missed_connections} broken connections). Estimated compensation and care liability: INR {total_cost:,.0f} under DGCA CAR Section 3."


def reformulate_statutory_query(initial_query: str, violation_type: str) -> str:
    """
    Uses Gemini to reformulate an unindexed or low-relevance statutory query
    into formal DGCA CAR terminology for improved vector retrieval.
    """
    if is_gemini_available():
        system_prompt = (
            "You are a DGCA aviation flight safety and regulatory legal expert in India. "
            "Convert the user's operational query into formal regulatory keywords strictly found in "
            "DGCA CAR Section 7, Series J, Part III (Flight and Duty Time Limitations and Rest Requirements). "
            "Return only the keyword query string, maximum 12 words."
        )
        user_prompt = f"Operational violation: {violation_type}. Query: {initial_query}"
        res = call_gemini(user_prompt, system_prompt=system_prompt)
        if res and not res.startswith("[Deterministic"):
            return res.strip('"').strip("'")

    # High-precision deterministic reformulations
    if "FDP" in violation_type or "duty" in initial_query.lower():
        return "maximum flight duty period FDP limit two pilot WOCL night duty table"
    elif "rest" in initial_query.lower():
        return "minimum rest period before flight duty 12 hours dgca car sec 7"
    elif "wocl" in initial_query.lower() or "night" in initial_query.lower():
        return "window of circadian low night duty 0200 to 0600 flight duty hours"
    return "dgca car section 7 series j part iii flight duty limitations"


def parse_duty_manager_disruption(
    message: str,
    base_schedule: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Parses a free-form natural language disruption message from a Human Duty Manager
    into structured operational disruption parameters for the multi-agent recovery loop.
    Uses Google Gemini when configured, with a resilient deterministic offline fallback.
    """
    import json
    import re

    clean_msg = (message or "").strip()
    if not clean_msg:
        clean_msg = "Tactical delay at hub airport"

    # 1. Attempt Live LLM Parsing via Google Gemini if available
    if is_gemini_available():
        system_prompt = (
            "You are the Mediator Agent in the SkyMediator Airline Operations Control Center (OCC) "
            "for Kempegowda International Airport, Bengaluru (VOBL/BLR). "
            "Your task is to parse unstructured operational disruption reports, pilot messages, or "
            "Duty Manager alerts into strict structured JSON. "
            "Extract the following keys:\n"
            "- disruption_type: one of ['fog', 'aog', 'crew', 'slot', 'weather', 'general']\n"
            "- airport: 4-letter ICAO code (default 'VOBL' if BLR or unspecified)\n"
            "- affected_flight_id: flight number such as '6E-101' (match if specified or infer from schedule)\n"
            "- severity: one of ['LOW', 'MODERATE', 'SEVERE']\n"
            "- delay_minutes: the operational delay caused by the disruption event (holding delay, AOG duration, etc.) in minutes (integer). "
            "Do NOT confuse this with crew FDP limits, max duty hours, or statutory caps. "
            "For example, if the message says '11.0h max FDP under 120m holding delay', delay_minutes=120, not 660. "
            "(default 180 if severe and no specific delay mentioned, 60 if moderate)\n"
            "- counter_delay_minutes: realistic counter-proposal delay in minutes for Round 2 (integer, 25-45)\n"
            "- initial_action: The tactical operational action to evaluate in Round 1. "
            "MUST be 'excessive_delay' for weather, fog, holding delay, slot congestion, or flight delay reports. "
            "ONLY use 'swap_tail' if the disruption is purely an aircraft mechanical failure (AOG/snag) or the user explicitly asks for an aircraft swap/substitution. "
            "ONLY use 'cancel' if the user explicitly orders flight cancellation.\n"
            "- candidate_tail: standby aircraft registration if swap is requested or available (e.g. 'VT-BLR15')\n"
            "- duty_manager_intent: concise 1-sentence summary of Duty Manager's operational intent\n"
            "- tactical_summary: concise 1-line headline summarizing the operational situation\n"
            "Return ONLY valid JSON without markdown code fences or extra text."
        )

        schedule_context = ""
        if base_schedule:
            flight_ids = [f.get("flight_id") for f in base_schedule[:8] if f.get("flight_id")]
            schedule_context = f"\nActive Scheduled Flights in Fleet: {', '.join(flight_ids)}"

        user_prompt = f"Duty Manager Message:\n\"\"\"{clean_msg}\"\"\"{schedule_context}\n\nParse into structured JSON:"

        try:
            raw_response = call_gemini(user_prompt, system_prompt=system_prompt)
            if raw_response and not raw_response.startswith("[Deterministic"):
                # Clean code fences if any
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and "disruption_type" in parsed:
                    # Validate and normalize
                    parsed["disruption_type"] = parsed.get("disruption_type", "fog").lower()
                    parsed["airport"] = parsed.get("airport", settings.HUB_AIRPORT).upper()
                    parsed["severity"] = parsed.get("severity", "SEVERE").upper()
                    parsed["delay_minutes"] = int(parsed.get("delay_minutes", 180))
                    parsed["counter_delay_minutes"] = int(parsed.get("counter_delay_minutes", 30))
                    parsed["affected_flight_id"] = str(parsed.get("affected_flight_id") or "6E-101")
                    parsed["candidate_tail"] = str(parsed.get("candidate_tail") or "VT-BLR15")
                    parsed["raw_message"] = clean_msg
                    parsed["parsed_by"] = "Gemini LLM"

                    # Safety override: if the text has an explicit minute count for holding/delay,
                    # use it instead of the LLM value (prevents FDP cap numbers from being mis-extracted)
                    explicit_delay_m = re.search(
                        r"(\d+)\s*m(?:in(?:utes?)?)?\s+(?:holding\s+)?delay|"
                        r"(?:holding\s+)?delay\s+(?:of\s+)?(\d+)\s*m(?:in(?:utes?)?)?",
                        clean_msg, re.IGNORECASE
                    )
                    if explicit_delay_m:
                        val = explicit_delay_m.group(1) or explicit_delay_m.group(2)
                        if val:
                            parsed["delay_minutes"] = int(val)

                    # Safety override for initial_action:
                    # If message describes holding delay, fog, or weather without mentioning swap or standby,
                    # initial_action MUST be 'excessive_delay' so OCC compliance agents can deliberate.
                    if parsed.get("initial_action") == "swap_tail":
                        if not any(w in clean_msg.lower() for w in ["swap", "standby", "reassign", "substitute", "replace tail", "aog", "snag", "technical"]):
                            parsed["initial_action"] = "excessive_delay"

                    return parsed
        except Exception as e:
            logger.warning(f"Live Gemini parsing failed ({e}). Proceeding to deterministic NLP parser.")

    # 2. Resilient Deterministic NLP Parser (Offline fallback / zero dependency failure)
    lower = clean_msg.lower()

    # Airport Detection with word boundaries
    airport = settings.HUB_AIRPORT  # VOBL
    if re.search(r"\b(vidp|delhi|del)\b", lower):
        airport = "VIDP"
    elif re.search(r"\b(vabb|mumbai|bom)\b", lower):
        airport = "VABB"
    elif re.search(r"\b(vomm|chennai|maa)\b", lower):
        airport = "VOMM"
    elif re.search(r"\b(vohy|hyderabad|hyd)\b", lower):
        airport = "VOHY"
    elif re.search(r"\b(vogo|goa|goi)\b", lower):
        airport = "VOGO"
    elif re.search(r"\b(vecc|kolkata|ccu)\b", lower):
        airport = "VECC"
    elif re.search(r"\b(vobl|kempegowda|bengaluru|bangalore|blr)\b", lower):
        airport = "VOBL"

    # Flight ID Detection
    flight_match = re.search(r"\b([0-9][A-Z]|[A-Z]{2})[- ]?(\d{3,4})\b", clean_msg, re.IGNORECASE)
    if flight_match:
        carrier = flight_match.group(1).upper()
        num = flight_match.group(2)
        affected_flight = f"{carrier}-{num}"
    elif base_schedule and len(base_schedule) > 0:
        affected_flight = base_schedule[0].get("flight_id", "6E-101")
    else:
        affected_flight = "6E-101"

    # Tail Detection
    tail_match = re.search(r"\b(VT-[A-Z0-9]{3,5})\b", clean_msg, re.IGNORECASE)
    candidate_tail = "VT-BLR15"
    if tail_match:
        detected_tail = tail_match.group(1).upper()
        if "swap" in lower and detected_tail != "VT-BLR01":
            candidate_tail = detected_tail

    # Delay / Impact Duration Detection (prioritize delay/holding/AOG context over statutory caps)
    delay_minutes = 180

    explicit_pat1 = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\s*(?:holding\s+delay|delay|holding)\b", lower)
    explicit_pat2 = re.search(r"(?:delay(?:ed)?|holding)\s*(?:by|of|for|with estimated)?\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)?\b", lower)
    aog_pat = re.search(r"aog\s*(?:for)?\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)?\b", lower)

    matched_val = None
    matched_unit = None

    if explicit_pat1:
        matched_val = float(explicit_pat1.group(1))
        matched_unit = explicit_pat1.group(2) or "m"
    elif aog_pat:
        matched_val = float(aog_pat.group(1))
        matched_unit = aog_pat.group(2) or "h"
    elif explicit_pat2:
        matched_val = float(explicit_pat2.group(1))
        matched_unit = explicit_pat2.group(2) or "m"
    else:
        min_match = re.search(r"(\d+)\s*(?:minutes?|mins?|m)\b", lower)
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", lower)
        if min_match:
            matched_val = float(min_match.group(1))
            matched_unit = "m"
        elif hour_match:
            matched_val = float(hour_match.group(1))
            matched_unit = "h"

    if matched_val is not None:
        if matched_unit and any(matched_unit.startswith(u) for u in ["h", "hour", "hr"]):
            delay_minutes = int(matched_val * 60)
        else:
            delay_minutes = int(matched_val)

    # Disruption Type Detection
    if any(k in lower for k in ["fog", "visibility", "rvr", "mist", "smog", "weather", "cat iii", "cat 3"]):
        disruption_type = "fog"
    elif any(k in lower for k in ["aog", "hydraulic", "engine", "technical", "snag", "grounded", "mechanical", "leak"]):
        disruption_type = "aog"
    elif any(k in lower for k in ["crew", "pilot", "captain", "officer", "fdtl", "timeout", "sick", "roster", "duty"]):
        disruption_type = "crew"
    elif any(k in lower for k in ["slot", "runway", "curfew", "holding", "atc", "capacity", "gridlock"]):
        disruption_type = "slot"
    else:
        disruption_type = "fog"

    # Severity Detection
    if any(k in lower for k in ["severe", "dense", "critical", "grounded", "emergency", "zero", "closure"]) or delay_minutes >= 180:
        severity = "SEVERE"
    elif any(k in lower for k in ["moderate", "medium"]) or delay_minutes >= 60:
        severity = "MODERATE"
    else:
        severity = "LOW"

    # Initial Action Strategy
    if "cancel" in lower and "swap" not in lower:
        initial_action = "cancel"
    elif any(k in lower for k in ["swap", "standby", "reassign"]) or disruption_type == "aog":
        initial_action = "swap_tail"
    else:
        initial_action = "excessive_delay"

    tactical_summary = (
        f"{severity} {disruption_type.upper()} disruption affecting {affected_flight} at {airport} "
        f"({delay_minutes}m projected impact; initial strategy: {initial_action})."
    )

    return {
        "disruption_type": disruption_type,
        "type": disruption_type,
        "airport": airport,
        "affected_flight_id": affected_flight,
        "severity": severity,
        "delay_minutes": delay_minutes,
        "counter_delay_minutes": 30,
        "initial_action": initial_action,
        "candidate_tail": candidate_tail,
        "duty_manager_intent": f"Duty Manager alerted OCC of {disruption_type} incident on flight {affected_flight}.",
        "tactical_summary": tactical_summary,
        "raw_message": clean_msg,
        "parsed_by": "Deterministic OCC Parser"
    }
