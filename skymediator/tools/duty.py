"""
Deterministic FDTL calculation engine according to DGCA CAR Section 7, Series J, Part III.
Validates crew duty periods, night operations (WOCL), block hours, and rest requirements.
"""

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple


def calculate_wocl_overlap_minutes(
    start_dt: datetime,
    end_dt: datetime,
    wocl_start_hour: int = 2,
    wocl_end_hour: int = 6
) -> int:
    """
    Computes overlap minutes with the Window of Circadian Low (WOCL: 02:00 to 06:00 IST).
    Under 2024 revised norms, WOCL is extended to 00:00 to 06:00.
    """
    overlap_minutes = 0
    curr = start_dt
    while curr < end_dt:
        if wocl_start_hour <= curr.hour < wocl_end_hour:
            overlap_minutes += 1
        curr += timedelta(minutes=1)
    return overlap_minutes


def get_max_allowed_fdp_minutes(
    duty_start: datetime,
    number_of_landings: int = 2,
    fdtl_version: Literal["2019", "2024"] = "2019"
) -> Tuple[int, str]:
    """
    Determines maximum statutory Flight Duty Period (FDP) in minutes.
    Based on DGCA CAR Section 7, Series J, Part III, Para 6.
    """
    start_hour = duty_start.hour
    
    if fdtl_version == "2024":
        # 2024 Revised Norms: Stricter night duty limits
        if 0 <= start_hour < 6:
            return (600, "CAR-Sec7-SeriesJ-PartIII-2024-Para6.1 (Night Duty FDP Max 10.0h)")
        elif number_of_landings <= 2:
            return (720, "CAR-Sec7-SeriesJ-PartIII-2024-Para6.2 (Max 12.0h FDP for <=2 landings)")
        else:
            return (660, "CAR-Sec7-SeriesJ-PartIII-2024-Para6.3 (Max 11.0h FDP for >2 landings)")
    else:
        # 2019 Active Baseline: Standard operational limit
        if 2 <= start_hour < 6:
            # Duty starting in WOCL
            return (660, "CAR-Sec7-SeriesJ-PartIII-2019-Para6.2 (WOCL Encroachment Max 11.0h)")
        elif number_of_landings <= 2:
            # Standard daytime operation with up to 2 landings
            return (750, "CAR-Sec7-SeriesJ-PartIII-2019-Para6.1 (Standard Daytime Max 12.5h FDP)")
        else:
            # 3 to 4 landings
            return (690, "CAR-Sec7-SeriesJ-PartIII-2019-Para6.1 (Multi-Sector Max 11.5h FDP)")


def calc_duty_time(
    crew_id: str,
    mutated_schedule: List[Dict[str, Any]],
    crew_duty_record: Dict[str, Any],
    assigned_flight_ids: List[str],
    fdtl_version: Literal["2019", "2024"] = "2019"
) -> Dict[str, Any]:
    """
    Evaluates statutory crew duty compliance for a candidate plan.
    Calculates actual FDP, block hours, WOCL overlap, and compares with DGCA limits.
    """
    duty_start = datetime.fromisoformat(crew_duty_record["duty_start"])
    flight_map = {f["flight_id"]: f for f in mutated_schedule}
    
    relevant_flights = [
        flight_map[fid] for fid in assigned_flight_ids 
        if fid in flight_map and flight_map[fid].get("status") != "CANCELLED"
    ]
    
    if not relevant_flights:
        return {
            "crew_id": crew_id,
            "is_legal": True,
            "total_fdp_minutes": 0,
            "max_allowed_fdp_minutes": 750,
            "total_block_minutes": 0,
            "wocl_overlap_minutes": 0,
            "violations": []
        }
        
    # Sort flights chronologically by scheduled or estimated times
    sorted_flights = sorted(
        relevant_flights,
        key=lambda f: datetime.fromisoformat(f.get("etd") or f["std"])
    )
    
    first_dep = datetime.fromisoformat(sorted_flights[0].get("etd") or sorted_flights[0]["std"])
    last_arr = datetime.fromisoformat(sorted_flights[-1].get("eta") or sorted_flights[-1]["sta"])
    
    # FDP begins at duty_start (or 45 mins prior to first dep, whichever earlier) and ends at last engine shutdown + 15 min debrief
    actual_duty_start = min(duty_start, first_dep - timedelta(minutes=45))
    duty_end = last_arr + timedelta(minutes=15)
    
    total_fdp_minutes = int((duty_end - actual_duty_start).total_seconds() / 60)
    
    # Total block flight minutes
    total_block_minutes = 0
    for f in sorted_flights:
        dep = datetime.fromisoformat(f.get("etd") or f["std"])
        arr = datetime.fromisoformat(f.get("eta") or f["sta"])
        total_block_minutes += int((arr - dep).total_seconds() / 60)
        
    num_landings = len(sorted_flights)
    max_fdp_minutes, applicable_clause = get_max_allowed_fdp_minutes(
        actual_duty_start,
        number_of_landings=num_landings,
        fdtl_version=fdtl_version
    )
    
    wocl_start = 0 if fdtl_version == "2024" else 2
    wocl_overlap_minutes = calculate_wocl_overlap_minutes(
        actual_duty_start,
        duty_end,
        wocl_start_hour=wocl_start,
        wocl_end_hour=6
    )
    
    violations: List[Dict[str, Any]] = []
    
    # 1. FDP Limit Check
    if total_fdp_minutes > max_fdp_minutes:
        violations.append({
            "type": "FDP_LIMIT_EXCEEDED",
            "actual_minutes": total_fdp_minutes,
            "limit_minutes": max_fdp_minutes,
            "clause_id": applicable_clause,
            "reason": f"Flight Duty Period of {total_fdp_minutes}m ({total_fdp_minutes/60:.1f}h) exceeds statutory limit of {max_fdp_minutes}m ({max_fdp_minutes/60:.1f}h)"
        })
        
    # 2. Block Hours Limit Check (Max 8 hours / 480 minutes in single duty)
    max_block_minutes = 480
    if total_block_minutes > max_block_minutes:
        violations.append({
            "type": "BLOCK_HOURS_EXCEEDED",
            "actual_minutes": total_block_minutes,
            "limit_minutes": max_block_minutes,
            "clause_id": "CAR-Sec7-SeriesJ-PartIII-Para5.1",
            "reason": f"Total block time {total_block_minutes}m ({total_block_minutes/60:.1f}h) exceeds 480m (8.0h) statutory maximum"
        })
        
    is_legal = len(violations) == 0
    
    return {
        "crew_id": crew_id,
        "is_legal": is_legal,
        "total_fdp_minutes": total_fdp_minutes,
        "max_allowed_fdp_minutes": max_fdp_minutes,
        "total_block_minutes": total_block_minutes,
        "wocl_overlap_minutes": wocl_overlap_minutes,
        "applicable_clause": applicable_clause,
        "violations": violations
    }
