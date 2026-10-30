"""
Deterministic synthetic data generator and scenario fixtures for Bengaluru Hub (VOBL/BLR).
Generates 15 aircraft, 24-hour flights, crew duties, passenger connections, and slot capacities.
"""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Optional, Union
from pathlib import Path

from skymediator.config import settings
from skymediator.db import get_connection, init_db


def seed_database(db_path: Optional[Union[str, Path]] = None, seed: int = 42) -> None:
    """Populates SQLite database with deterministic, relational operational data."""
    init_db(db_path)
    conn = get_connection(db_path)
    
    # Reference date: 2026-11-01 (Bengaluru Winter Tactical Window)
    base_time = datetime(2026, 11, 1, 4, 0, 0)  # 04:00 AM IST
    
    # 1. Seed Cost Rates
    cost_rates = [
        ("delay_per_min", 150.0, "INR", "Operational cost per flight delay minute (fuel/crew/ground)"),
        ("cancel_base", 250000.0, "INR", "Base airline penalty for flight cancellation"),
        ("meal_voucher", 500.0, "INR", "DGCA CAR Sec 3 mandatory meal voucher for delays >= 2 hours"),
        ("hotel_night", 3500.0, "INR", "DGCA CAR Sec 3 hotel accommodation for overnight delays"),
        ("dgca_comp", 5000.0, "INR", "DGCA CAR Sec 3 passenger statutory compensation"),
        ("crew_overtime_hr", 2000.0, "INR", "Crew overtime penalty rate per hour beyond scheduled duty")
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO cost_rates (item, rate, currency, description) VALUES (?, ?, ?, ?)",
        cost_rates
    )

    # 2. Seed 15 Aircraft (Diverse Narrow-body & Regional Fleet based at VOBL/BLR)
    fleet_specs = [
        # (tail, type, seats, min_turn_min, airport, maint_hours)
        ("VT-BLR01", "A320neo", 186, 35, "VOBL", 145.0),
        ("VT-BLR02", "A320neo", 186, 35, "VOBL", 110.0),
        ("VT-BLR03", "A320neo", 186, 35, "VOBL", 85.0),
        ("VT-BLR04", "A320neo", 186, 35, "VOBL", 160.0),
        ("VT-BLR05", "A321neo", 222, 45, "VOBL", 130.0),
        ("VT-BLR06", "A321neo", 222, 45, "VOBL", 95.0),
        ("VT-BLR07", "A321neo", 232, 45, "VOBL", 175.0),
        ("VT-BLR08", "A321neo", 232, 45, "VOBL", 120.0),
        ("VT-BLR09", "A320ceo", 180, 35, "VOBL", 65.0),
        ("VT-BLR10", "A320ceo", 180, 35, "VOBL", 140.0),
        ("VT-BLR11", "A320ceo", 180, 35, "VOBL", 75.0),
        ("VT-BLR12", "A320ceo", 180, 35, "VOBL", 115.0),
        ("VT-BLR13", "ATR72-600", 78, 25, "VOBL", 90.0),
        ("VT-BLR14", "ATR72-600", 78, 25, "VOBL", 50.0),
        ("VT-BLR15", "A320neo", 186, 35, "VOBL", 180.0),  # Standby Reserve
    ]
    tails = [spec[0] for spec in fleet_specs]
    seats_map = {spec[0]: spec[2] for spec in fleet_specs}

    conn.executemany(
        "INSERT OR REPLACE INTO aircraft (tail, aircraft_type, seats, min_turn_min, current_airport, maintenance_due_hours) VALUES (?, ?, ?, ?, ?, ?)",
        fleet_specs
    )

    # 3. Seed Scheduled Flights (Diverse Indian sectors with realistic stage-length durations)
    routes = [
        ("VOBL", "VIDP", 165),  # BLR -> DEL (165m)
        ("VIDP", "VOBL", 160),  # DEL -> BLR (160m)
        ("VOBL", "VABB", 105),  # BLR -> BOM (105m)
        ("VABB", "VOBL", 100),  # BOM -> BLR (100m)
        ("VOBL", "VECC", 155),  # BLR -> CCU (155m)
        ("VECC", "VOBL", 150),  # CCU -> BLR (150m)
        ("VOBL", "VOMM", 55),   # BLR -> MAA (55m)
        ("VOMM", "VOBL", 50),   # MAA -> BLR (50m)
        ("VOBL", "VOHY", 70),   # BLR -> HYD (70m)
        ("VOHY", "VOBL", 70),   # HYD -> BLR (70m)
        ("VOBL", "VOGO", 75),   # BLR -> GOI (75m)
        ("VOGO", "VOBL", 70),   # GOI -> BLR (70m)
    ]
    
    flights_data = []
    flight_num = 101
    
    for day_offset in range(2):  # 24 hour rotation
        for i, tail in enumerate(tails):
            # Assign regional routes to ATR aircraft, trunk routes to A321/A320
            if tail in ("VT-BLR13", "VT-BLR14"):
                regional_routes = [("VOBL", "VOMM", 55), ("VOMM", "VOBL", 50), ("VOBL", "VOHY", 70), ("VOHY", "VOBL", 70), ("VOBL", "VOGO", 75), ("VOGO", "VOBL", 70)]
                route = regional_routes[(i + day_offset) % len(regional_routes)]
            else:
                route = routes[(i + day_offset * 3) % len(routes)]

            dep_time = base_time + timedelta(hours=i * 1.2 + day_offset * 12)
            arr_time = dep_time + timedelta(minutes=route[2])
            flight_id = f"6E-{flight_num}"
            flight_num += 1
            seats = seats_map.get(tail, 180)
            
            flights_data.append((
                flight_id,
                tail,
                route[0],
                route[1],
                dep_time.isoformat(),
                arr_time.isoformat(),
                dep_time.isoformat(),
                arr_time.isoformat(),
                seats,
                "SCHEDULED"
            ))

    conn.executemany(
        """INSERT OR REPLACE INTO flights 
        (flight_id, tail, origin, dest, std, sta, etd, eta, seats, status) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        flights_data
    )

    # 4. Seed Crew Members & Duties
    crew_members = [
        ("CREW-CAPT-01", "Capt. Vikram Rao", "CAPTAIN", "VOBL", "VOBL", 15.0),
        ("CREW-FO-01", "FO. Priya Sharma", "FIRST_OFFICER", "VOBL", "VOBL", 12.0),
        ("CREW-CAPT-02", "Capt. Rohit Sen", "CAPTAIN", "VOBL", "VOBL", 28.0),
        ("CREW-FO-02", "FO. Ananya Iyer", "FIRST_OFFICER", "VOBL", "VOBL", 24.0),
        ("CREW-CAPT-03", "Capt. Arvind Nair", "CAPTAIN", "VOBL", "VOBL", 8.0),
        ("CREW-FO-03", "FO. Sneha Reddy", "FIRST_OFFICER", "VOBL", "VOBL", 6.0),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO crew_members (crew_id, name, role, base, current_airport, cumulative_duty_7d_hours) VALUES (?, ?, ?, ?, ?, ?)",
        crew_members
    )

    # Seed duty periods: Capt Rao assigned to 6E-101 and 6E-102
    duties = [
        ("DUTY-01", "CREW-CAPT-01", (base_time - timedelta(hours=1)).isoformat(), None, 720, 750, 0, 0),
        ("DUTY-02", "CREW-FO-01", (base_time - timedelta(hours=1)).isoformat(), None, 720, 750, 0, 0),
        ("DUTY-03", "CREW-CAPT-02", (base_time - timedelta(hours=8)).isoformat(), None, 720, 750, 0, 0), # Already on 8hr duty!
        ("DUTY-04", "CREW-FO-02", (base_time - timedelta(hours=8)).isoformat(), None, 720, 750, 0, 0),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO crew_duties (duty_id, crew_id, duty_start, duty_end, rest_period_before_min, max_fdp_minutes, is_split_duty, is_augmented) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        duties
    )

    crew_duty_flights = [
        ("DUTY-01", "6E-101", 1, 0),
        ("DUTY-02", "6E-101", 1, 0),
        ("DUTY-03", "6E-103", 1, 0),
        ("DUTY-04", "6E-103", 1, 0),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO crew_duty_flights (duty_id, flight_id, leg_sequence, is_deadhead) VALUES (?, ?, ?, ?)",
        crew_duty_flights
    )

    # 5. Seed Airport Slot Windows for VOBL
    # Disrupted fog period: 05:00 to 08:30 (capacity = 8), normal capacity = 20
    slot_windows = []
    slot_start = base_time
    for s_idx in range(48):  # 48 half-hour windows (24 hours)
        w_start = slot_start + timedelta(minutes=s_idx * 30)
        w_end = w_start + timedelta(minutes=30)
        is_fog = 5 <= w_start.hour < 9
        capacity = 8 if is_fog else 20
        slot_windows.append(("VOBL", w_start.isoformat(), w_end.isoformat(), capacity, "23:30", "04:30"))

    conn.executemany(
        "INSERT OR REPLACE INTO slots (airport, window_start, window_end, capacity, curfew_start, curfew_end) VALUES (?, ?, ?, ?, ?, ?)",
        slot_windows
    )

    # 6. Seed Passenger Bookings and Connections through VOBL
    bookings = [
        ("BKG-001", 4, "BUSINESS", 12000.0, "pax1@corp.in"),
        ("BKG-002", 15, "ECONOMY", 4500.0, "group2@travel.in"),
        ("BKG-003", 2, "ECONOMY", 5200.0, "pax3@family.in"),
        ("BKG-004", 1, "PREMIUM_ECON", 8000.0, "solo@work.in"),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO bookings (booking_id, pax_count, fare_class, avg_fare_paid, contact_email) VALUES (?, ?, ?, ?, ?)",
        bookings
    )

    # Connecting flight 6E-102 (arr VOBL at 08:00) -> 6E-105 (dep VOBL at 09:15), connect min = 45 min
    connections = [
        ("BKG-001", "6E-102", "6E-105", "VOBL", 45),
        ("BKG-002", "6E-102", "6E-105", "VOBL", 45),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO connections (booking_id, inbound_flight, outbound_flight, connection_airport, min_connect_min) VALUES (?, ?, ?, ?, ?)",
        connections
    )

    # 7. Seed Standard Scenarios
    scenarios = [
        (
            "SCENARIO_BLR_FOG_SUCCESS",
            "Morning Winter Fog at Kempegowda Hub",
            "fog",
            "VOBL",
            (base_time + timedelta(hours=1)).isoformat(),
            (base_time + timedelta(hours=4)).isoformat(),
            "MODERATE",
            "MEDIUM",
            json.dumps({"affected_flight": "6E-101", "viable_alternative": "VT-BLR15"})
        ),
        (
            "SCENARIO_BLR_FOG_CREW_VETO",
            "Cascading Fog Causing Crew Duty Timeout",
            "fog",
            "VOBL",
            (base_time + timedelta(hours=1)).isoformat(),
            (base_time + timedelta(hours=5)).isoformat(),
            "SEVERE",
            "HARD",
            json.dumps({"affected_flight": "6E-103", "duty_exceedance_minutes": 90})
        ),
        (
            "SCENARIO_BLR_SLOT_VETO",
            "Peak Hour Slot Saturation at Hub",
            "fog",
            "VOBL",
            (base_time + timedelta(hours=2)).isoformat(),
            (base_time + timedelta(hours=4)).isoformat(),
            "SEVERE",
            "HARD",
            json.dumps({"target_window": "06:00-06:30", "slot_capacity": 8})
        )
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO scenarios (scenario_id, name, disruption_type, airport, start_time, end_time, severity, difficulty, seeded_anomalies) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        scenarios
    )

    conn.commit()
    conn.close()


def reset_all_data(db_path: Optional[Union[str, Path]] = None) -> None:
    """Completely wipes historical deliberation runs, events, decisions, and resets to clean base fixtures."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        # Clear audit and execution tables
        for tbl in ["agent_events", "decision_records", "plan_revisions", "flights", "aircraft", "crew_members", "crew_duties", "crew_duty_flights", "bookings", "connections", "scenarios"]:
            try:
                conn.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    seed_database(db_path)
    from skymediator.ingest.make_scenarios import seed_scenarios
    seed_scenarios(db_path)

