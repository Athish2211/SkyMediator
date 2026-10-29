"""
Curated scenario builder for SkyMediator.
Seeds 10 reproducible evaluation scenarios (5 standard + 5 adversarial).
"""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skymediator.config import settings
from skymediator.db import get_connection, init_db


def build_scenario_records(base_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
    base = base_date or datetime(2026, 11, 1, 5, 0)

    scenarios = [
        # --- 5 Standard Disruption Scenarios ---
        {
            "scenario_id": "SCENARIO_01_MILD_FOG",
            "name": "Mild Morning Fog at Kempegowda Hub",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=1)).isoformat(),
            "end_time": (base + timedelta(hours=3)).isoformat(),
            "severity": "LOW",
            "difficulty": "EASY",
            "seeded_anomalies": json.dumps({
                "affected_flight_id": "6E-101",
                "runway_capacity": 12,
                "description": "Visibility drops to 800m. 4 flights delayed; manageable tail swap available."
            })
        },
        {
            "scenario_id": "SCENARIO_02_SEVERE_CAT3_FOG",
            "name": "Severe CAT III Radiation Fog at Kempegowda Hub",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": base.isoformat(),
            "end_time": (base + timedelta(hours=4)).isoformat(),
            "severity": "SEVERE",
            "difficulty": "HARD",
            "seeded_anomalies": json.dumps({
                "affected_flight_id": "6E-101",
                "runway_capacity": 6,
                "initial_action": "excessive_delay",
                "delay_minutes": 240,
                "description": "RVR drops to 250m. Runway capacity reduced by 65%. Crew duty near WOCL limit."
            })
        },
        {
            "scenario_id": "SCENARIO_03_AOG_OUTSTATION",
            "name": "Aircraft on Ground (AOG) Snag at Delhi",
            "disruption_type": "aog",
            "airport": "VIDP",
            "start_time": (base + timedelta(hours=2)).isoformat(),
            "end_time": (base + timedelta(hours=8)).isoformat(),
            "severity": "MODERATE",
            "difficulty": "MEDIUM",
            "seeded_anomalies": json.dumps({
                "affected_tail": "VT-BLR03",
                "grounded_flight_id": "6E-105",
                "description": "Hydraulic leak on VT-BLR03 at VIDP requires 6 hours maintenance. Requires tail swap."
            })
        },
        {
            "scenario_id": "SCENARIO_04_CASCADING_ROTATION",
            "name": "Multi-Sector Delay Cascading from Kolkata",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=3)).isoformat(),
            "end_time": (base + timedelta(hours=7)).isoformat(),
            "severity": "MODERATE",
            "difficulty": "MEDIUM",
            "seeded_anomalies": json.dumps({
                "affected_flight_id": "6E-107",
                "delay_propagation_count": 3,
                "description": "Inbound flight delayed 110m, threatening turnaround of next 3 flights."
            })
        },
        {
            "scenario_id": "SCENARIO_05_CURFEW_CONFLICT",
            "name": "Late Evening Flight Threatening Night Curfew",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=14)).isoformat(),
            "end_time": (base + timedelta(hours=18)).isoformat(),
            "severity": "MODERATE",
            "difficulty": "HARD",
            "seeded_anomalies": json.dumps({
                "affected_flight_id": "6E-119",
                "projected_arrival": "23:45",
                "curfew_time": "23:30",
                "description": "Flight delay pushes arrival past destination curfew. Requires swap or cancellation."
            })
        },

        # --- 5 Adversarial / Robustness Scenarios ---
        {
            "scenario_id": "SCENARIO_06_MISSING_CONNECTION_DATA",
            "name": "Corrupt Itinerary with Null Minimum Connection Time",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=1)).isoformat(),
            "end_time": (base + timedelta(hours=4)).isoformat(),
            "severity": "MODERATE",
            "difficulty": "ADVERSARIAL",
            "seeded_anomalies": json.dumps({
                "corrupt_field": "min_connect_min",
                "corrupt_booking_id": "BKG-CONN-CORRUPT",
                "expected_behavior": "Default to 45m buffer and log audit warning without crashing."
            })
        },
        {
            "scenario_id": "SCENARIO_07_SEAT_SATURATION",
            "name": "Zero Available Seats on All Rebooking Alternatives",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=2)).isoformat(),
            "end_time": (base + timedelta(hours=6)).isoformat(),
            "severity": "SEVERE",
            "difficulty": "ADVERSARIAL",
            "seeded_anomalies": json.dumps({
                "alternative_flight_load_factor": 1.0,
                "expected_behavior": "Flag unrebookable passengers and assess hotel/compensation penalty."
            })
        },
        {
            "scenario_id": "SCENARIO_08_AMBIGUOUS_WOCL_FDTL",
            "name": "Split Duty Crossing Window of Circadian Low Boundary",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=1)).isoformat(),
            "end_time": (base + timedelta(hours=6)).isoformat(),
            "severity": "SEVERE",
            "difficulty": "ADVERSARIAL",
            "seeded_anomalies": json.dumps({
                "duty_start": "01:55",
                "wocl_boundary": "02:00",
                "expected_behavior": "Agentic RAG must retrieve specific split-duty clause or abstain with escalation."
            })
        },
        {
            "scenario_id": "SCENARIO_09_TOTAL_SLOT_GRIDLOCK",
            "name": "Runway Closure with Zero Movement Slots",
            "disruption_type": "fog",
            "airport": "VOBL",
            "start_time": (base + timedelta(hours=2)).isoformat(),
            "end_time": (base + timedelta(hours=5)).isoformat(),
            "severity": "SEVERE",
            "difficulty": "ADVERSARIAL",
            "seeded_anomalies": json.dumps({
                "slot_capacity": 0,
                "expected_behavior": "Veto all delays into window; propose controlled cancellations or diversions."
            })
        },
        {
            "scenario_id": "SCENARIO_10_UNCREWED_OUTSTATION",
            "name": "Uncrewed Leg at Outstation with Zero Local Reserve",
            "disruption_type": "fog",
            "airport": "VOGO",
            "start_time": (base + timedelta(hours=4)).isoformat(),
            "end_time": (base + timedelta(hours=9)).isoformat(),
            "severity": "SEVERE",
            "difficulty": "ADVERSARIAL",
            "seeded_anomalies": json.dumps({
                "outstation": "VOGO",
                "local_reserves": 0,
                "expected_behavior": "Detect missing crew base; propose deadheading crew or flight cancellation."
            })
        }
    ]

    return scenarios


def seed_scenarios(db_path: Optional[Path] = None) -> int:
    """Seeds all 10 standard and adversarial scenarios into SQLite database."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        scenarios = build_scenario_records()
        rows = [
            (
                s["scenario_id"],
                s["name"],
                s["disruption_type"],
                s["airport"],
                s["start_time"],
                s["end_time"],
                s["severity"],
                s["difficulty"],
                s["seeded_anomalies"]
            )
            for s in scenarios
        ]

        conn.executemany(
            """INSERT OR REPLACE INTO scenarios 
            (scenario_id, name, disruption_type, airport, start_time, end_time, severity, difficulty, seeded_anomalies)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Seed 10 standard and adversarial disruption scenarios.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    count = seed_scenarios()
    print(f"Successfully seeded {count} disruption scenarios (5 standard + 5 adversarial).")


if __name__ == "__main__":
    main()
