"""
Tests for Gemini LLM integration module and historical dataset ingestion.
"""

from pathlib import Path
from skymediator.config import settings
from skymediator.llm import (
    get_gemini_api_key,
    is_gemini_available,
    call_gemini,
    synthesize_occ_briefing,
    reformulate_statutory_query
)
from skymediator.ingest.fetch_historic_data import (
    HISTORICAL_METAR_CSV,
    HISTORICAL_ROUTES_CSV
)
from skymediator.agents.sentinel import SentinelAgent


def test_llm_fallback_and_briefing_synthesis(monkeypatch):
    # Test deterministic fallback when no API key is provided
    monkeypatch.setattr("skymediator.llm.is_gemini_available", lambda: False)
    briefing = synthesize_occ_briefing(
        plan={
            "plan_id": "PLAN-R1-TEST",
            "plan_diff": [
                {"op": "swap_tail", "flight_id": "6E-101", "original_tail": "VT-BLR01", "new_tail": "VT-BLR15"},
                {"op": "delay", "flight_id": "6E-202", "delay_minutes": 30}
            ]
        },
        scores={"composite_score": 0.045, "raw_metrics": {"delay_minutes": 30.0, "total_cost": 4500.0}},
        disruption={"type": "fog", "airport": "VOBL"},
        hub="VOBL (BLR)"
    )

    assert "OCC Executive Recovery Briefing" in briefing or "VOBL" in briefing
    assert "Tail Swap" in briefing
    assert "Tactical Delay" in briefing
    assert "DGCA CAR Section 7" in briefing


def test_llm_statutory_query_reformulation():
    query = reformulate_statutory_query(
        initial_query="pilot duty timeout 13 hours",
        violation_type="FDP exceedance"
    )
    assert len(query) > 0
    assert any(keyword in query.lower() for keyword in ["fdp", "duty", "wocl", "night", "dgca", "car"])


def test_historical_datasets_presence_and_sentinel_training():
    # 1. Historical METAR CSV for Kempegowda Hub must be present
    assert HISTORICAL_METAR_CSV.exists()
    assert HISTORICAL_METAR_CSV.stat().st_size > 10_000  # More than 10KB of real weather data

    # 2. Historical Indian domestic flight route benchmarks must be present
    assert HISTORICAL_ROUTES_CSV.exists()
    assert HISTORICAL_ROUTES_CSV.stat().st_size > 500

    # 3. SentinelAgent must successfully train on real historical dataset
    sentinel = SentinelAgent(airport="VOBL")
    assert sentinel.pipeline is not None
    assert sentinel.training_brier_score is not None
    assert sentinel.training_brier_score < 0.20
