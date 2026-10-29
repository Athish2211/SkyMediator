"""
Unit and integration tests for SentinelAgent.
Verifies fog prediction, ML feature extraction, calibrated Brier score, and advisory recommendations.
"""

from datetime import datetime
from skymediator.agents.sentinel import SentinelAgent, SentinelOutput


def test_sentinel_initialization_and_brier_score():
    sentinel = SentinelAgent(airport="VOBL")
    assert sentinel.pipeline is not None
    assert sentinel.training_brier_score is not None
    # Well-calibrated probabilistic classifier must have Brier score < 0.20
    assert sentinel.training_brier_score < 0.20


def test_sentinel_detects_severe_fog():
    sentinel = SentinelAgent(airport="VOBL")
    # Low visibility (300m), low RVR (250m), narrow dewpoint depression (0.2C), morning window
    fog_obs = {
        "station": "VOBL",
        "ts": datetime(2026, 11, 1, 5, 30).isoformat(),
        "visibility_m": 300,
        "rvr_m": 250,
        "dewpoint_depression": 0.2,
        "wind_speed_kts": 2.0,
        "cloud_ceiling_ft": 150,
        "is_morning_window": 1,
        "present_weather": ["FG"]
    }

    output: SentinelOutput = sentinel.evaluate_forecast(fog_obs, run_id="TEST-SENTINEL-FOG")
    assert output.disruption_detected is True
    assert output.event_type == "fog"
    assert output.probability >= 0.50
    assert output.recommended_action in ["pre_position", "act_early"]
    assert output.expected_lead_time_hours > 0.0
    # Rationale may be LLM-synthesized or deterministic — check structural content
    rat = output.rationale.lower()
    assert len(rat) > 10, "Rationale must be non-empty"
    assert any(kw in rat for kw in [
        "fog", "rvr", "visibility", "radiation", "cat", "disruption", "risk", "probability"
    ]), f"Fog-case rationale should reference weather risk, got: {rat}"


def test_sentinel_passes_clear_weather():
    sentinel = SentinelAgent(airport="VOBL")
    # CAVOK: visibility 8000m, high dewpoint depression, afternoon
    clear_obs = {
        "station": "VOBL",
        "ts": datetime(2026, 11, 1, 14, 0).isoformat(),
        "visibility_m": 8000,
        "rvr_m": 3000,
        "dewpoint_depression": 6.5,
        "wind_speed_kts": 8.0,
        "cloud_ceiling_ft": 4000,
        "is_morning_window": 0,
        "present_weather": []
    }

    output: SentinelOutput = sentinel.evaluate_forecast(clear_obs, run_id="TEST-SENTINEL-CLEAR")
    assert output.disruption_detected is False
    assert output.event_type == "none"
    assert output.probability < 0.45
    assert output.recommended_action == "monitor"
    # Rationale may be LLM-synthesized (dynamic) or deterministic fallback.
    # Assert structural correctness: must be a non-empty string about a low-risk/clear condition.
    rat = output.rationale.lower()
    assert len(rat) > 10, "Rationale must be non-empty"
    # Either the deterministic fallback or an LLM sentence about monitor/low/clear conditions
    assert any(kw in rat for kw in [
        "low fog risk", "low", "monitor", "minimal", "clear", "unrestricted", "stable", "normal", "advisory", "cavok"
    ]), f"Clear-weather rationale should reference low risk or advisory status, got: {rat}"
