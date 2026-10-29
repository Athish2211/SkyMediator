"""
Unit tests for flight schedule generation and fleet rotation validity.
"""

from datetime import datetime
from pathlib import Path
from skymediator.ingest.fetch_schedule import generate_fleet_rotations, seed_schedule_and_aircraft
from skymediator.db import get_connection


def test_generate_fleet_rotations_scale_and_continuity():
    flights = generate_fleet_rotations(num_aircraft=15)
    assert len(flights) == 60  # 15 aircraft * 4 legs each = 60 flights

    # Group flights by aircraft tail and verify turnaround buffers
    tails = set(f["tail"] for f in flights)
    assert len(tails) == 15

    for tail in tails:
        tail_flights = [f for f in flights if f["tail"] == tail]
        assert len(tail_flights) == 4

        # Chronological order
        for idx in range(len(tail_flights) - 1):
            curr_leg = tail_flights[idx]
            next_leg = tail_flights[idx + 1]

            # Physical airport continuity
            assert curr_leg["dest"] == next_leg["origin"], f"Discontinuity for {tail}: {curr_leg['dest']} != {next_leg['origin']}"

            # Turnaround buffer >= 35 minutes
            arr_time = datetime.fromisoformat(curr_leg["sta"])
            dep_time = datetime.fromisoformat(next_leg["std"])
            turnaround_mins = int((dep_time - arr_time).total_seconds() / 60)
            assert turnaround_mins >= 35, f"Turnaround violation for {tail}: {turnaround_mins}m < 35m"


def test_seed_schedule_and_aircraft(tmp_path: Path):
    db_file = tmp_path / "sched_test.db"
    count = seed_schedule_and_aircraft(db_path=db_file)
    assert count == 60

    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM aircraft")
    assert cur.fetchone()[0] == 15

    cur.execute("SELECT COUNT(*) FROM flights WHERE origin = 'VOBL' OR dest = 'VOBL'")
    assert cur.fetchone()[0] == 60
    conn.close()
