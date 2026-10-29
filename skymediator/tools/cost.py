"""
Deterministic financial cost estimation engine.
Calculates flight delay costs, cancellation penalties, and DGCA CAR Section 3 statutory passenger care liabilities.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from skymediator.config import settings
from skymediator.db import get_connection


def get_cost_rates(db_path: Optional[Union[str, Path]] = None) -> Dict[str, float]:
    """Retrieves operational and regulatory unit cost rates from SQLite."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT item, rate FROM cost_rates")
        return {r["item"]: float(r["rate"]) for r in cursor.fetchall()}
    finally:
        conn.close()


def estimate_cost(
    mutated_schedule: List[Dict[str, Any]],
    missed_connections_count: int = 0,
    affected_bookings: Optional[List[Dict[str, Any]]] = None,
    rates: Optional[Dict[str, float]] = None,
    db_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Computes exact itemized operational and passenger care costs.
    Applies DGCA CAR Section 3, Series M, Part IV thresholds:
    - Free meals for delays >= 120 minutes
    - Free hotel accommodation for overnight or >= 24-hour delays
    """
    unit_rates = rates or get_cost_rates(db_path)
    rate_delay_min = unit_rates.get("delay_per_min", 150.0)
    rate_cancel = unit_rates.get("cancel_base", 250000.0)
    rate_meal = unit_rates.get("meal_voucher", 500.0)
    rate_hotel = unit_rates.get("hotel_night", 3500.0)
    rate_comp = unit_rates.get("dgca_comp", 5000.0)

    total_delay_minutes = 0.0
    cancelled_flight_count = 0
    pax_needing_meals = 0
    pax_needing_hotel = 0
    pax_statutory_comp = 0

    for flight in mutated_schedule:
        status = flight.get("status", "SCHEDULED")
        pax_on_board = int(flight.get("seats", 180) * 0.85)  # 85% load factor

        if status == "CANCELLED":
            cancelled_flight_count += 1
            # DGCA CAR Sec 3: Alternate flight or refund + statutory compensation
            pax_statutory_comp += pax_on_board
        else:
            std_dt = datetime.fromisoformat(flight["std"])
            etd_dt = datetime.fromisoformat(flight.get("etd") or flight["std"])
            delay_mins = max(0, int((etd_dt - std_dt).total_seconds() / 60))

            if delay_mins > 0:
                total_delay_minutes += delay_mins

            # DGCA CAR Sec 3: Delays >= 2 hours trigger mandatory meals
            if delay_mins >= 120:
                pax_needing_meals += pax_on_board

            # DGCA CAR Sec 3: Overnight delays trigger hotel accommodation
            if delay_mins >= 360 or (etd_dt.day > std_dt.day):
                pax_needing_hotel += pax_on_board

    # Connection breakage care
    pax_needing_hotel += missed_connections_count * 2  # Average 2 pax per connection needing overnight stay

    delay_cost = total_delay_minutes * rate_delay_min
    cancel_cost = cancelled_flight_count * rate_cancel
    meal_cost = pax_needing_meals * rate_meal
    hotel_cost = pax_needing_hotel * rate_hotel
    comp_cost = pax_statutory_comp * rate_comp

    total_cost = delay_cost + cancel_cost + meal_cost + hotel_cost + comp_cost

    return {
        "delay_cost": round(delay_cost, 2),
        "cancellation_cost": round(cancel_cost, 2),
        "meal_care_cost": round(meal_cost, 2),
        "hotel_care_cost": round(hotel_cost, 2),
        "statutory_compensation_cost": round(comp_cost, 2),
        "total_cost": round(total_cost, 2),
        "currency": "INR",
        "quantities": {
            "total_delay_minutes": total_delay_minutes,
            "cancelled_flights": cancelled_flight_count,
            "passengers_provided_meals": pax_needing_meals,
            "passengers_provided_hotels": pax_needing_hotel,
            "statutory_compensations_paid": pax_statutory_comp
        }
    }
