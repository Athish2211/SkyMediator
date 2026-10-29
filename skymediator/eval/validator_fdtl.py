"""
Clean-Room Independent FDTL Validator (resolving GAP-03 & PROP-05).
Strictly decoupled from runtime agent tools. 
Used exclusively for evaluation and academic benchmarks to verify 0.00% regulatory violation rates.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List


def validate_plan_independent(
    mutated_schedule: Any,
    crew_rosters: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Independent clean-room verification of candidate plans against DGCA CAR Section 7.
    Does NOT import tools/duty.py to guarantee non-circular evaluation.
    """
    if isinstance(mutated_schedule, dict):
        schedule_list = mutated_schedule.get("mutated_flights", [])
    else:
        schedule_list = list(mutated_schedule or [])

    violations: List[Dict[str, Any]] = []
    flight_map = {f["flight_id"]: f for f in schedule_list if f.get("status") != "CANCELLED"}

    for crew in crew_rosters:
        crew_id = crew["crew_id"]
        duty_start = datetime.fromisoformat(crew["duty_start"])
        assigned_flights = crew.get("assigned_flights", [])

        operating_flights = [flight_map[fid] for fid in assigned_flights if fid in flight_map]
        if not operating_flights:
            continue

        # Sort chronologically
        sorted_flights = sorted(
            operating_flights,
            key=lambda x: datetime.fromisoformat(x.get("etd") or x["std"])
        )

        dep_first = datetime.fromisoformat(sorted_flights[0].get("etd") or sorted_flights[0]["std"])
        arr_last = datetime.fromisoformat(sorted_flights[-1].get("eta") or sorted_flights[-1]["sta"])

        # Official DGCA reporting time: 45 min prior to departure
        calc_start = min(duty_start, dep_first - timedelta(minutes=45))
        calc_end = arr_last + timedelta(minutes=15)  # 15 min debrief

        fdp_minutes = int((calc_end - calc_start).total_seconds() / 60)

        # Baseline CAR limits
        max_limit = 750  # 12.5 hours daytime
        if 2 <= calc_start.hour < 6:
            max_limit = 660  # 11.0 hours WOCL

        if fdp_minutes > max_limit:
            violations.append({
                "crew_id": crew_id,
                "violation": "FDP_LIMIT_EXCEEDED",
                "actual_fdp": fdp_minutes,
                "statutory_limit": max_limit,
                "clause": "DGCA CAR Section 7, Series J, Part III"
            })

    return {
        "is_compliant": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations
    }
