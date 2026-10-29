"""
Unit tests for the clean-room independent FDTL validator (eval/validator_fdtl.py).
"""

from skymediator.eval.validator_fdtl import validate_plan_independent


def test_independent_validator_passes_compliant_schedule():
    schedule = [
        {"flight_id": "6E-101", "std": "2026-11-01T07:00:00", "sta": "2026-11-01T09:30:00", "status": "SCHEDULED"},
        {"flight_id": "6E-102", "std": "2026-11-01T10:30:00", "sta": "2026-11-01T13:00:00", "status": "SCHEDULED"}
    ]
    rosters = [
        {"crew_id": "CREW-01", "duty_start": "2026-11-01T06:00:00", "assigned_flights": ["6E-101", "6E-102"]}
    ]

    res = validate_plan_independent(schedule, rosters)
    assert res["is_compliant"] is True
    assert res["violation_count"] == 0


def test_independent_validator_flags_illegal_schedule():
    schedule = [
        {"flight_id": "6E-101", "std": "2026-11-01T05:00:00", "sta": "2026-11-01T07:30:00", "status": "SCHEDULED"},
        {"flight_id": "6E-102", "std": "2026-11-01T16:00:00", "sta": "2026-11-01T19:00:00", "status": "DELAYED"}
    ]
    rosters = [
        {"crew_id": "CREW-01", "duty_start": "2026-11-01T04:00:00", "assigned_flights": ["6E-101", "6E-102"]}
    ]

    res = validate_plan_independent(schedule, rosters)
    assert res["is_compliant"] is False
    assert res["violation_count"] == 1
    assert res["violations"][0]["violation"] == "FDP_LIMIT_EXCEEDED"
