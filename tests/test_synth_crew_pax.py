"""
Unit tests for synthetic crew, passenger, and connection generation reproducibility.
"""

from pathlib import Path
from skymediator.ingest.synth_crew_pax import generate_crew_and_passenger_data, seed_synthetic_data
from skymediator.db import get_connection


def test_synthetic_data_reproducibility():
    # Fixed seed must produce identical counts and IDs
    data_1 = generate_crew_and_passenger_data(seed=42)
    data_2 = generate_crew_and_passenger_data(seed=42)

    assert len(data_1["crew_members"]) == len(data_2["crew_members"]) == 24
    assert len(data_1["crew_duties"]) == len(data_2["crew_duties"]) == 24
    assert len(data_1["bookings"]) == len(data_2["bookings"])
    assert len(data_1["connections"]) == len(data_2["connections"])

    # Check identical booking IDs
    assert [b[0] for b in data_1["bookings"]] == [b[0] for b in data_2["bookings"]]


def test_seed_synthetic_data(tmp_path: Path):
    db_file = tmp_path / "synth_test.db"
    counts = seed_synthetic_data(db_path=db_file, seed=42)

    assert counts["crew_members"] == 24
    assert counts["slot_windows"] == 48
    assert counts["connections"] > 0

    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM crew_members WHERE role IN ('CAPTAIN', 'FIRST_OFFICER')")
    assert cur.fetchone()[0] == 24

    cur.execute("PRAGMA foreign_key_check")
    assert len(cur.fetchall()) == 0
    conn.close()
