"""
Unit tests for scenario generation and categorization.
"""

from pathlib import Path
from skymediator.ingest.make_scenarios import build_scenario_records, seed_scenarios
from skymediator.db import get_connection


def test_build_scenario_records():
    scenarios = build_scenario_records()
    assert len(scenarios) == 10

    standard = [s for s in scenarios if s["difficulty"] in ["EASY", "MEDIUM", "HARD"]]
    adversarial = [s for s in scenarios if s["difficulty"] == "ADVERSARIAL"]

    assert len(standard) == 5
    assert len(adversarial) == 5

    # Check key adversarial scenario IDs
    scen_ids = [s["scenario_id"] for s in scenarios]
    assert "SCENARIO_02_SEVERE_CAT3_FOG" in scen_ids
    assert "SCENARIO_06_MISSING_CONNECTION_DATA" in scen_ids
    assert "SCENARIO_08_AMBIGUOUS_WOCL_FDTL" in scen_ids


def test_seed_scenarios(tmp_path: Path):
    db_file = tmp_path / "scen_test.db"
    count = seed_scenarios(db_path=db_file)
    assert count == 10

    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM scenarios")
    assert cur.fetchone()[0] == 10
    conn.close()
