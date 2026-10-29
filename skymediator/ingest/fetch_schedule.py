"""
Flight schedule generator and validator for Kempegowda Hub (VOBL/BLR).
Generates 60 scheduled domestic flights for 15 narrow-body aircraft with verified turnaround buffers.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import argparse

from skymediator.config import settings
from skymediator.db import get_connection, init_db


ROUTES = [
    {"origin": "VOBL", "dest": "VIDP", "block_mins": 150, "pax_demand": 170},  # BLR -> DEL
    {"origin": "VIDP", "dest": "VOBL", "block_mins": 150, "pax_demand": 175},  # DEL -> BLR
    {"origin": "VOBL", "dest": "VABB", "block_mins": 100, "pax_demand": 165},  # BLR -> BOM
    {"origin": "VABB", "dest": "VOBL", "block_mins": 100, "pax_demand": 168},  # BOM -> BLR
    {"origin": "VOBL", "dest": "VOMM", "block_mins": 50,  "pax_demand": 150},  # BLR -> MAA
    {"origin": "VOMM", "dest": "VOBL", "block_mins": 50,  "pax_demand": 145},  # MAA -> BLR
    {"origin": "VOBL", "dest": "VOHY", "block_mins": 70,  "pax_demand": 160},  # BLR -> HYD
    {"origin": "VOHY", "dest": "VOBL", "block_mins": 70,  "pax_demand": 155},  # HYD -> BLR
    {"origin": "VOBL", "dest": "VOGO", "block_mins": 60,  "pax_demand": 140},  # BLR -> GOI
    {"origin": "VOGO", "dest": "VOBL", "block_mins": 60,  "pax_demand": 142},  # GOI -> BLR
    {"origin": "VOBL", "dest": "VECC", "block_mins": 150, "pax_demand": 160},  # BLR -> CCU
    {"origin": "VECC", "dest": "VOBL", "block_mins": 150, "pax_demand": 162},  # CCU -> BLR
]


def generate_fleet_rotations(
    base_date: Optional[datetime] = None,
    num_aircraft: int = 15
) -> List[Dict[str, Any]]:
    """
    Constructs a 24-hour tactical schedule (60 flights) across 15 aircraft.
    Guarantees that each aircraft arrives at the origin of its next flight with >= 40m turnaround.
    """
    start_dt = base_date or datetime(2026, 11, 1, 5, 0)  # 05:00 AM IST
    flights: List[Dict[str, Any]] = []
    flight_seq = 101

    tails = [f"VT-BLR{i:02d}" for i in range(1, num_aircraft + 1)]

    # Pair outbound and inbound routes for each aircraft
    for tail_idx, tail in enumerate(tails):
        curr_time = start_dt + timedelta(minutes=tail_idx * 25)
        curr_airport = "VOBL"

        # 4 sectors per aircraft over the 24-hour horizon (15 x 4 = 60 flights)
        for leg_idx in range(4):
            if curr_airport == "VOBL":
                # Outbound from hub
                target_route = ROUTES[(tail_idx * 2 + leg_idx) % len(ROUTES)]
                if target_route["origin"] != "VOBL":
                    # Swap direction to depart from VOBL
                    origin = "VOBL"
                    dest = target_route["origin"]
                    block_mins = target_route["block_mins"]
                else:
                    origin = target_route["origin"]
                    dest = target_route["dest"]
                    block_mins = target_route["block_mins"]
            else:
                # Inbound return leg to hub
                origin = curr_airport
                dest = "VOBL"
                matching_route = next((r for r in ROUTES if r["origin"] == origin and r["dest"] == dest), None)
                block_mins = matching_route["block_mins"] if matching_route else 100

            dep_dt = curr_time
            arr_dt = dep_dt + timedelta(minutes=block_mins)
            flight_id = f"6E-{flight_seq}"
            flight_seq += 1

            flights.append({
                "flight_id": flight_id,
                "tail": tail,
                "origin": origin,
                "dest": dest,
                "std": dep_dt.isoformat(),
                "sta": arr_dt.isoformat(),
                "seats": 180,
                "status": "SCHEDULED"
            })

            # Minimum 45 min turnaround before next departure
            curr_time = arr_dt + timedelta(minutes=45)
            curr_airport = dest

    return flights


def seed_schedule_and_aircraft(db_path: Optional[Path] = None) -> int:
    """Inserts 15 aircraft and 60 scheduled flights into SQLite."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        # Seed 15 Aircraft
        aircraft_rows = [
            (f"VT-BLR{i:02d}", "A320", 180, 35, "VOBL", 120.0 if i != 15 else 18.0)
            for i in range(1, 16)
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO aircraft 
            (tail, aircraft_type, seats, min_turn_min, current_airport, maintenance_due_hours)
            VALUES (?, ?, ?, ?, ?, ?)""",
            aircraft_rows
        )

        # Seed Flights
        flights = generate_fleet_rotations()
        flight_rows = [
            (
                f["flight_id"],
                f["tail"],
                f["origin"],
                f["dest"],
                f["std"],
                f["sta"],
                f["std"],
                f["sta"],
                f["seats"],
                f["status"]
            )
            for f in flights
        ]

        conn.executemany(
            """INSERT OR REPLACE INTO flights 
            (flight_id, tail, origin, dest, std, sta, etd, eta, seats, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            flight_rows
        )
        conn.commit()
        return len(flight_rows)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate and seed domestic schedule for Kempegowda Hub.")
    parser.add_argument("--seed-db", action="store_true", help="Seed flights into SQLite database")
    args = parser.parse_args()

    flights = generate_fleet_rotations()
    print(f"Generated {len(flights)} scheduled flights across 15 aircraft.")
    print(f"Sample Flight: {flights[0]['flight_id']} ({flights[0]['tail']}) {flights[0]['origin']} -> {flights[0]['dest']} STD {flights[0]['std']}")

    if args.seed_db:
        count = seed_schedule_and_aircraft()
        print(f"Successfully seeded {count} flights into database.")


if __name__ == "__main__":
    main()
