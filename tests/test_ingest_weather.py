"""
Unit tests for weather ingestion and METAR feature extraction.
"""

from pathlib import Path
from skymediator.ingest.fetch_weather import (
    generate_synthetic_winter_metar,
    extract_fog_features,
    seed_weather_observations
)
from skymediator.db import get_connection


def test_generate_synthetic_winter_metar():
    obs = generate_synthetic_winter_metar("VOBL", num_hours=24)
    assert len(obs) == 24
    assert obs[0]["station"] == "VOBL"
    assert "METAR VOBL" in obs[0]["metar_raw"]

    # Morning fog hours (05:00 to 08:00) should have low visibility
    morning_obs = [o for o in obs if 5 <= int(o["ts"].split("T")[1].split(":")[0]) <= 8]
    assert len(morning_obs) > 0
    assert all(o["visibility_m"] <= 600 for o in morning_obs)


def test_extract_fog_features():
    sample = {
        "ts": "2026-11-01T06:00:00",
        "visibility_m": 350,
        "rvr_m": 300,
        "temp_c": 16.5,
        "dewpoint_c": 16.0,
        "wind_speed_kts": 3,
        "cloud_ceiling_ft": 200
    }
    feats = extract_fog_features(sample)
    assert feats["visibility_m"] == 350.0
    assert feats["dewpoint_depression"] == 0.5
    assert feats["is_morning_window"] == 1.0


def test_seed_weather_observations(tmp_path: Path):
    db_file = tmp_path / "weather_test.db"
    count = seed_weather_observations(db_path=db_file, station="VOBL")
    assert count == 48

    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM weather_obs WHERE station = 'VOBL'")
    assert cur.fetchone()[0] == 48
    conn.close()
