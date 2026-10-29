"""
Synthetic crew and passenger generator for SkyMediator.
Anchors crew pairings and passenger itineraries to real scheduled flights.
Guarantees byte-for-byte reproducibility using explicit pseudo-random seeds.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import random
from typing import Any, Dict, List, Optional

from skymediator.config import settings
from skymediator.db import get_connection, init_db
from skymediator.ingest.fetch_schedule import generate_fleet_rotations


def generate_crew_and_passenger_data(seed: int = 42) -> Dict[str, Any]:
    """Generates synthetic crew duties, passenger bookings, and connecting itineraries."""
    random.seed(seed)
    flights = generate_fleet_rotations()

    # 1. Generate 24 Crew Members (12 Captains + 12 First Officers)
    crew_members = []
    crew_duties = []
    crew_duty_flights = []

    for i in range(1, 13):
        capt_id = f"CREW-CAPT-{i:02d}"
        fo_id = f"CREW-FO-{i:02d}"

        crew_members.append((capt_id, f"Capt. Pilot {i}", "CAPTAIN", "VOBL", "VOBL", round(random.uniform(5.0, 25.0), 1)))
        crew_members.append((fo_id, f"FO. Pilot {i}", "FIRST_OFFICER", "VOBL", "VOBL", round(random.uniform(5.0, 22.0), 1)))

        # Assign 2 flight legs per crew duty (e.g. BLR -> DEL -> BLR)
        fl_1 = flights[(i - 1) * 2]
        fl_2 = flights[(i - 1) * 2 + 1]

        duty_start = datetime.fromisoformat(fl_1["std"]) - timedelta(minutes=45)
        duty_id_capt = f"DUTY-C{i:02d}"
        duty_id_fo = f"DUTY-F{i:02d}"

        crew_duties.append((duty_id_capt, capt_id, duty_start.isoformat(), None, 720, 750, 0, 0))
        crew_duties.append((duty_id_fo, fo_id, duty_start.isoformat(), None, 720, 750, 0, 0))

        crew_duty_flights.append((duty_id_capt, fl_1["flight_id"], 1, 0))
        crew_duty_flights.append((duty_id_capt, fl_2["flight_id"], 2, 0))
        crew_duty_flights.append((duty_id_fo, fl_1["flight_id"], 1, 0))
        crew_duty_flights.append((duty_id_fo, fl_2["flight_id"], 2, 0))

    # 2. Generate Passenger Bookings & Connecting Itineraries through VOBL
    bookings = []
    itinerary_legs = []
    connections = []

    bkg_id_seq = 1001

    # Single-leg bookings
    for fl in flights:
        pax_count = random.randint(1, 4)
        fare_class = random.choice(["ECONOMY", "ECONOMY", "ECONOMY", "PREMIUM_ECON", "BUSINESS"])
        avg_fare = 4200.0 if fare_class == "ECONOMY" else (7500.0 if fare_class == "PREMIUM_ECON" else 14000.0)

        bid = f"BKG-{bkg_id_seq}"
        bkg_id_seq += 1

        bookings.append((bid, pax_count, fare_class, avg_fare, f"pax{bid}@client.com"))
        itinerary_legs.append((bid, 1, fl["flight_id"], f"{random.randint(1,30)}{random.choice('ABCDEF')}"))

    # Multi-leg Connecting Bookings through VOBL Hub
    # Find flight pairs where inbound lands at VOBL, outbound departs VOBL 45–180 mins later
    for i in range(len(flights) - 1):
        in_fl = flights[i]
        if in_fl["dest"] == "VOBL":
            in_arr = datetime.fromisoformat(in_fl["sta"])
            for j in range(len(flights)):
                out_fl = flights[j]
                if out_fl["origin"] == "VOBL" and out_fl["flight_id"] != in_fl["flight_id"]:
                    out_dep = datetime.fromisoformat(out_fl["std"])
                    diff_mins = int((out_dep - in_arr).total_seconds() / 60)
                    if 45 <= diff_mins <= 150:
                        bid = f"BKG-CONN-{bkg_id_seq}"
                        bkg_id_seq += 1
                        pax_count = random.randint(1, 3)

                        bookings.append((bid, pax_count, "ECONOMY", 8500.0, f"connect_{bid}@airline.com"))
                        itinerary_legs.append((bid, 1, in_fl["flight_id"], "12A"))
                        itinerary_legs.append((bid, 2, out_fl["flight_id"], "14B"))
                        connections.append((bid, in_fl["flight_id"], out_fl["flight_id"], "VOBL", 45))
                        break

    # 3. Airport Slot Windows (24 hours in 30-min increments)
    slot_windows = []
    base_time = datetime(2026, 11, 1, 4, 0)
    for idx in range(48):
        w_start = base_time + timedelta(minutes=idx * 30)
        w_end = w_start + timedelta(minutes=30)
        is_fog = 5 <= w_start.hour < 9
        capacity = 8 if is_fog else 20
        slot_windows.append(("VOBL", w_start.isoformat(), w_end.isoformat(), capacity, "23:30", "04:30"))

    return {
        "crew_members": crew_members,
        "crew_duties": crew_duties,
        "crew_duty_flights": crew_duty_flights,
        "bookings": bookings,
        "itinerary_legs": itinerary_legs,
        "connections": connections,
        "slot_windows": slot_windows
    }


def seed_synthetic_data(db_path: Optional[Path] = None, seed: int = 42) -> Dict[str, int]:
    """Populates SQLite database with deterministic synthetic entities."""
    init_db(db_path)
    from skymediator.ingest.fetch_schedule import seed_schedule_and_aircraft
    seed_schedule_and_aircraft(db_path)
    conn = get_connection(db_path)
    try:
        data = generate_crew_and_passenger_data(seed=seed)

        conn.executemany(
            """INSERT OR REPLACE INTO crew_members 
            (crew_id, name, role, base, current_airport, cumulative_duty_7d_hours)
            VALUES (?, ?, ?, ?, ?, ?)""",
            data["crew_members"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO crew_duties 
            (duty_id, crew_id, duty_start, duty_end, rest_period_before_min, max_fdp_minutes, is_split_duty, is_augmented)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            data["crew_duties"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO crew_duty_flights (duty_id, flight_id, leg_sequence, is_deadhead)
            VALUES (?, ?, ?, ?)""",
            data["crew_duty_flights"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO bookings (booking_id, pax_count, fare_class, avg_fare_paid, contact_email)
            VALUES (?, ?, ?, ?, ?)""",
            data["bookings"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO itinerary_legs (booking_id, leg_no, flight_id, seat_assigned)
            VALUES (?, ?, ?, ?)""",
            data["itinerary_legs"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO connections (booking_id, inbound_flight, outbound_flight, connection_airport, min_connect_min)
            VALUES (?, ?, ?, ?, ?)""",
            data["connections"]
        )

        conn.executemany(
            """INSERT OR REPLACE INTO slots (airport, window_start, window_end, capacity, curfew_start, curfew_end)
            VALUES (?, ?, ?, ?, ?, ?)""",
            data["slot_windows"]
        )

        conn.commit()
        return {k: len(v) for k, v in data.items()}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Seed deterministic synthetic crew and passenger data.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    counts = seed_synthetic_data(seed=args.seed)
    print("Synthetic Data Generation Complete:")
    for entity, count in counts.items():
        print(f" - {entity}: {count} records")


if __name__ == "__main__":
    main()
