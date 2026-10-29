"""
Unit tests for deterministic passenger tools and connection impact calculations.
"""

from pathlib import Path
from skymediator.fixtures import seed_database
from skymediator.tools.passengers import get_affected_bookings, calc_missed_connections, get_rebooking_options


def test_get_affected_bookings(tmp_path: Path):
    db_file = tmp_path / "pax_test.db"
    seed_database(db_file)

    bookings = get_affected_bookings(["6E-101", "6E-102"], db_path=db_file)
    # Seeded flights 101/102 have associated bookings
    assert isinstance(bookings, list)


def test_calc_missed_connections():
    # Inbound lands at 08:30. Outbound scheduled departure is 09:00.
    # Buffer is 30 mins < 45 mins min_connect_min -> CONNECTION BROKEN!
    mutated_schedule = [
        {"flight_id": "6E-102", "origin": "VIDP", "dest": "VOBL", "std": "2026-11-01T06:00:00", "sta": "2026-11-01T08:30:00", "status": "SCHEDULED"},
        {"flight_id": "6E-105", "origin": "VOBL", "dest": "VOMM", "std": "2026-11-01T09:00:00", "sta": "2026-11-01T09:50:00", "status": "SCHEDULED"}
    ]

    res = calc_missed_connections(mutated_schedule)
    assert "total_missed_connections" in res
    assert "broken_connection_records" in res


def test_get_rebooking_options(tmp_path: Path):
    db_file = tmp_path / "rebook_test.db"
    seed_database(db_file)

    schedule = [
        {"flight_id": "6E-101", "tail": "VT-BLR01", "origin": "VOBL", "dest": "VIDP", "std": "2026-11-01T06:00:00", "sta": "2026-11-01T08:30:00", "status": "SCHEDULED"},
        {"flight_id": "6E-103", "tail": "VT-BLR02", "origin": "VOBL", "dest": "VIDP", "std": "2026-11-01T09:00:00", "sta": "2026-11-01T11:30:00", "status": "SCHEDULED"}
    ]

    res = get_rebooking_options("BKG-001", schedule, db_path=db_file)
    assert isinstance(res, dict)
    assert "feasible_options" in res
