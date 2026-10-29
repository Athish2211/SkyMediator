"""
Unit tests for deterministic cost estimation and DGCA CAR Section 3 liabilities.
"""

from skymediator.tools.cost import estimate_cost


def test_estimate_cost_delay_and_meals():
    # Flight delayed by 150 minutes (>= 120m -> triggers meal vouchers under DGCA CAR Sec 3)
    schedule = [
        {
            "flight_id": "6E-101",
            "std": "2026-11-01T06:00:00",
            "etd": "2026-11-01T08:30:00",
            "sta": "2026-11-01T08:30:00",
            "eta": "2026-11-01T11:00:00",
            "seats": 180,
            "status": "DELAYED"
        }
    ]

    rates = {
        "delay_per_min": 150.0,
        "cancel_base": 250000.0,
        "meal_voucher": 500.0,
        "hotel_night": 3500.0,
        "dgca_comp": 5000.0
    }

    res = estimate_cost(schedule, missed_connections_count=0, rates=rates)

    # Delay cost: 150 mins * 150 INR = 22,500 INR
    assert res["delay_cost"] == 22500.0

    # Meal cost: 180 seats * 0.85 = 153 pax * 500 INR = 76,500 INR
    assert res["meal_care_cost"] == 76500.0

    # Total cost: 22,500 + 76,500 = 99,000 INR
    assert res["total_cost"] == 99000.0
    assert res["cancellation_cost"] == 0.0


def test_estimate_cost_cancellation():
    schedule = [
        {
            "flight_id": "6E-101",
            "std": "2026-11-01T06:00:00",
            "sta": "2026-11-01T08:30:00",
            "seats": 180,
            "status": "CANCELLED"
        }
    ]

    rates = {
        "delay_per_min": 150.0,
        "cancel_base": 250000.0,
        "meal_voucher": 500.0,
        "hotel_night": 3500.0,
        "dgca_comp": 5000.0
    }

    res = estimate_cost(schedule, missed_connections_count=0, rates=rates)
    assert res["cancellation_cost"] == 250000.0
    # Statutory compensation: 153 pax * 5000 = 765,000 INR
    assert res["statutory_compensation_cost"] == 765000.0
    assert res["total_cost"] == 1015000.0
