"""
Unit tests for SkyMediator configuration and environment settings.
"""

from skymediator.config import Settings


def test_default_settings():
    s = Settings()
    assert s.HUB_AIRPORT == "VOBL"
    assert s.HUB_IATA == "BLR"
    assert s.FDTL_VERSION in ["2019", "2024"]
    assert s.MAX_NEGOTIATION_ROUNDS == 3
    assert s.NORMALIZATION_CAP_DELAY_MINUTES == 600.0
    assert sum(s.SCORING_WEIGHTS.values()) == 1.0


def test_custom_settings():
    s = Settings(HUB_AIRPORT="VIDP", FDTL_VERSION="2024", MAX_NEGOTIATION_ROUNDS=5)
    assert s.HUB_AIRPORT == "VIDP"
    assert s.FDTL_VERSION == "2024"
    assert s.MAX_NEGOTIATION_ROUNDS == 5
