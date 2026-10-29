"""
Unit tests for SQLite database schema and foreign key constraints.
"""

from pathlib import Path
import sqlite3
import pytest

from skymediator.db import init_db, get_connection
from skymediator.fixtures import seed_database


def test_init_db_and_foreign_keys(tmp_path: Path):
    db_file = tmp_path / "test.db"
    init_db(db_file)

    conn = get_connection(db_file)
    cursor = conn.execute("PRAGMA foreign_key_check;")
    violations = cursor.fetchall()
    assert len(violations) == 0, f"Foreign key violations found: {violations}"

    # Verify foreign key enforcement
    with pytest.raises(sqlite3.IntegrityError):
        # Insert flight with non-existent aircraft tail
        conn.execute(
            """INSERT INTO flights (flight_id, tail, origin, dest, std, sta, seats) 
            VALUES ('6E-999', 'NON_EXISTENT_TAIL', 'VOBL', 'VIDP', '2026-11-01 06:00', '2026-11-01 08:30', 180)"""
        )
    conn.close()


def test_seed_database(tmp_path: Path):
    db_file = tmp_path / "seeded_test.db"
    seed_database(db_file)

    conn = get_connection(db_file)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM aircraft;")
    assert cur.fetchone()[0] == 15

    cur.execute("SELECT COUNT(*) FROM flights;")
    assert cur.fetchone()[0] > 0

    cur.execute("SELECT COUNT(*) FROM scenarios;")
    assert cur.fetchone()[0] >= 3

    cur.execute("PRAGMA foreign_key_check;")
    assert len(cur.fetchall()) == 0

    conn.close()
