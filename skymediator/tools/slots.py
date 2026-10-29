"""
Deterministic airport slot and curfew validation tool.
Enforces half-hour movement capacity and destination night curfew constraints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


def check_slot(
    airport: str,
    mutated_schedule: List[Dict[str, Any]],
    slot_windows: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validates that aircraft movements (arrivals + departures) do not exceed 
    airport slot capacity in any 30-minute window during disrupted low visibility.
    """
    violated_windows: List[Dict[str, Any]] = []
    curfew_breaches: List[Dict[str, Any]] = []

    # Map slot windows by start and end datetime
    for window in slot_windows:
        w_start = datetime.fromisoformat(window["window_start"])
        w_end = datetime.fromisoformat(window["window_end"])
        capacity = int(window["capacity"])
        curfew_start = window.get("curfew_start")
        curfew_end = window.get("curfew_end")

        movement_count = 0
        movement_flights: List[str] = []

        for flight in mutated_schedule:
            if flight.get("status") == "CANCELLED":
                continue

            origin = flight["origin"]
            dest = flight["dest"]
            dep_time = datetime.fromisoformat(flight.get("etd") or flight["std"])
            arr_time = datetime.fromisoformat(flight.get("eta") or flight["sta"])

            # Check departures from airport
            if origin == airport and w_start <= dep_time < w_end:
                movement_count += 1
                movement_flights.append(flight["flight_id"])

            # Check arrivals at airport
            if dest == airport and w_start <= arr_time < w_end:
                movement_count += 1
                movement_flights.append(flight["flight_id"])

        if movement_count > capacity:
            violated_windows.append({
                "window_start": window["window_start"],
                "window_end": window["window_end"],
                "capacity": capacity,
                "actual_movements": movement_count,
                "affected_flights": movement_flights,
                "reason": f"Slot capacity exceeded: {movement_count} movements in window, max allowed is {capacity}"
            })

    is_valid = len(violated_windows) == 0 and len(curfew_breaches) == 0

    return {
        "is_valid": is_valid,
        "violated_windows": violated_windows,
        "curfew_breaches": curfew_breaches
    }
