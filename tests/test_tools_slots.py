"""
Unit tests for deterministic airport slot and curfew checks.
"""

from skymediator.tools.slots import check_slot


def test_slot_capacity_pass():
    schedule = [
        {
            "flight_id": "6E-101",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": "2026-11-01T06:10:00",
            "sta": "2026-11-01T08:40:00",
            "status": "SCHEDULED"
        }
    ]

    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": "2026-11-01T06:00:00",
            "window_end": "2026-11-01T06:30:00",
            "capacity": 8
        }
    ]

    res = check_slot("VOBL", schedule, slot_windows)
    assert res["is_valid"] is True
    assert len(res["violated_windows"]) == 0


def test_slot_capacity_exceeded_fails():
    # Capacity is 2, but 3 flights depart from VOBL within the 06:00-06:30 window
    schedule = [
        {"flight_id": "6E-101", "origin": "VOBL", "dest": "VIDP", "std": "2026-11-01T06:05:00", "sta": "2026-11-01T08:35:00", "status": "SCHEDULED"},
        {"flight_id": "6E-102", "origin": "VOBL", "dest": "VABB", "std": "2026-11-01T06:15:00", "sta": "2026-11-01T08:00:00", "status": "SCHEDULED"},
        {"flight_id": "6E-103", "origin": "VOBL", "dest": "VOMM", "std": "2026-11-01T06:25:00", "sta": "2026-11-01T07:15:00", "status": "SCHEDULED"},
    ]

    slot_windows = [
        {
            "airport": "VOBL",
            "window_start": "2026-11-01T06:00:00",
            "window_end": "2026-11-01T06:30:00",
            "capacity": 2
        }
    ]

    res = check_slot("VOBL", schedule, slot_windows)
    assert res["is_valid"] is False
    assert len(res["violated_windows"]) == 1
    assert res["violated_windows"][0]["actual_movements"] == 3
    assert res["violated_windows"][0]["capacity"] == 2
