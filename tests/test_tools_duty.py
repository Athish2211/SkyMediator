"""
Unit tests for deterministic FDTL duty time calculations against DGCA CAR Section 7.
"""

from datetime import datetime, timedelta

from skymediator.tools.duty import (
    calc_duty_time,
    calculate_wocl_overlap_minutes,
    get_max_allowed_fdp_minutes
)


def test_wocl_overlap_calculation():
    # Duty starting at 01:00 and ending at 07:00 IST
    # WOCL is 02:00 to 06:00 -> exactly 4 hours (240 minutes) overlap
    start_dt = datetime(2026, 11, 1, 1, 0)
    end_dt = datetime(2026, 11, 1, 7, 0)
    overlap = calculate_wocl_overlap_minutes(start_dt, end_dt)
    assert overlap == 240


def test_standard_daytime_fdp_pass():
    # Duty start at 06:00. Flight 1: 07:00-09:30. Flight 2: 10:30-13:00.
    # Total FDP = 06:00 to 13:15 = 7h 15m (435 minutes) <= 750 min limit -> PASS!
    base_schedule = [
        {
            "flight_id": "6E-101",
            "std": "2026-11-01T07:00:00",
            "sta": "2026-11-01T09:30:00",
            "status": "SCHEDULED"
        },
        {
            "flight_id": "6E-102",
            "std": "2026-11-01T10:30:00",
            "sta": "2026-11-01T13:00:00",
            "status": "SCHEDULED"
        }
    ]

    duty_record = {"duty_start": "2026-11-01T06:00:00"}
    res = calc_duty_time(
        crew_id="CREW-01",
        mutated_schedule=base_schedule,
        crew_duty_record=duty_record,
        assigned_flight_ids=["6E-101", "6E-102"],
        fdtl_version="2019"
    )

    assert res["is_legal"] is True
    assert res["total_fdp_minutes"] == 435
    assert len(res["violations"]) == 0


def test_fdp_exceedance_fails():
    # Duty start at 04:00 AM. Delayed Flight 2 ends at 18:00 (FDP = 14h 15m = 855 minutes).
    # Statutory limit is 660 mins (WOCL encroachment) or 750 mins (daytime) -> MUST FAIL!
    base_schedule = [
        {
            "flight_id": "6E-101",
            "std": "2026-11-01T05:00:00",
            "sta": "2026-11-01T07:30:00",
            "status": "SCHEDULED"
        },
        {
            "flight_id": "6E-102",
            "std": "2026-11-01T15:30:00",
            "sta": "2026-11-01T18:00:00",
            "status": "DELAYED"
        }
    ]

    duty_record = {"duty_start": "2026-11-01T04:00:00"}
    res = calc_duty_time(
        crew_id="CREW-01",
        mutated_schedule=base_schedule,
        crew_duty_record=duty_record,
        assigned_flight_ids=["6E-101", "6E-102"],
        fdtl_version="2019"
    )

    assert res["is_legal"] is False
    assert len(res["violations"]) > 0
    assert res["violations"][0]["type"] == "FDP_LIMIT_EXCEEDED"
    assert "CAR-Sec7-SeriesJ-PartIII" in res["violations"][0]["clause_id"]


def test_2024_revised_norms_toggle():
    # Under 2024 revised norms, night duty starting before 06:00 is capped strictly at 10.0h (600 mins)
    duty_start = datetime(2026, 11, 1, 3, 0)
    limit_2019, _ = get_max_allowed_fdp_minutes(duty_start, number_of_landings=2, fdtl_version="2019")
    limit_2024, _ = get_max_allowed_fdp_minutes(duty_start, number_of_landings=2, fdtl_version="2024")

    assert limit_2019 == 660  # 11.0h
    assert limit_2024 == 600  # 10.0h (Stricter!)
