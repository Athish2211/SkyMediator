"""
Evaluation Scenario Dataset Generator for SkyMediator.
Constructs 27 deterministic, reproducible disruption scenarios covering:
- 21 Standard and Stress Scenarios (Fog, AOG, Curfew, Rotation, Slots, Passenger Waves)
- 6 Explicitly Adversarial Scenarios (Corrupt data, Missing inputs, Hard constraint violations,
  Misleading low-cost alternatives, Regulatory ambiguity requiring abstention).

Outputs:
1. evaluation/scenarios/scenarios.json (Machine-readable scenario definitions)
2. evaluation/scenarios/scenario_annotations.json (Independent ground-truth feasibility labels)
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, List


def generate_evaluation_dataset() -> Dict[str, Any]:
    base_time = datetime(2026, 11, 1, 5, 0)
    scenarios: List[Dict[str, Any]] = []
    annotations: List[Dict[str, Any]] = []

    # 1. Low-severity fog disruption
    scenarios.append({
        "scenario_id": "SCEN-01-LOW-FOG",
        "name": "Low Severity Winter Fog at VOBL Hub",
        "category": "standard_fog",
        "severity": "LOW",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=3)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Morning mist reducing runway capacity to 14 movements/half-hour. Manageable 25m delay.",
        "weather_inputs": {
            "visibility_m": 850.0,
            "rvr_m": 750.0,
            "dewpoint_depression": 0.8,
            "wind_speed_kts": 3.0,
            "cloud_ceiling_ft": 400,
            "is_morning_window": 1.0
        },
        "affected_flight_id": "6E-101",
        "initial_action": "delay",
        "delay_minutes": 25,
        "counter_delay_minutes": 20,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 14,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 168,
        "connecting_pax_count": 22
    })
    annotations.append({
        "scenario_id": "SCEN-01-LOW-FOG",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "delay_25m",
        "known_feasible_alternatives": ["delay_25m", "swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 22500.0,
        "benchmark_compatibility": True
    })

    # 2. Moderate fog disruption
    scenarios.append({
        "scenario_id": "SCEN-02-MOD-FOG",
        "name": "Moderate Radiation Fog with Low Visibility Procedures",
        "category": "standard_fog",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=4)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Radiation fog reduces visibility to 450m. CAT II LVP implemented. 40m delay required.",
        "weather_inputs": {
            "visibility_m": 450.0,
            "rvr_m": 400.0,
            "dewpoint_depression": 0.4,
            "wind_speed_kts": 2.0,
            "cloud_ceiling_ft": 200,
            "is_morning_window": 1.0
        },
        "affected_flight_id": "6E-102",
        "initial_action": "delay",
        "delay_minutes": 45,
        "counter_delay_minutes": 35,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 10,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 174,
        "connecting_pax_count": 35
    })
    annotations.append({
        "scenario_id": "SCEN-02-MOD-FOG",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_standby_tail",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_35m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 38000.0,
        "benchmark_compatibility": True
    })

    # 3. Severe fog disruption
    scenarios.append({
        "scenario_id": "SCEN-03-SEVERE-FOG",
        "name": "Severe CAT III Radiation Fog at VOBL",
        "category": "stress_fog",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": base_time.isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Severe CAT III fog, RVR 200m. Capacity drops to 6 movements/30m. Initial 180m delay vetoed by crew.",
        "weather_inputs": {
            "visibility_m": 150.0,
            "rvr_m": 200.0,
            "dewpoint_depression": 0.1,
            "wind_speed_kts": 1.0,
            "cloud_ceiling_ft": 100,
            "is_morning_window": 1.0
        },
        "affected_flight_id": "6E-103",
        "initial_action": "excessive_delay",
        "delay_minutes": 220,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 6,
        "crew_duty_start": (base_time - timedelta(hours=3, minutes=30)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 48
    })
    annotations.append({
        "scenario_id": "SCEN-03-SEVERE-FOG",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "swap_tail_with_reserve_crew",
        "known_feasible_alternatives": ["swap_VT-BLR15", "selective_cancellation"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 85000.0,
        "benchmark_compatibility": True
    })

    # 4. Rapidly deteriorating visibility
    scenarios.append({
        "scenario_id": "SCEN-04-RAPID-VIS-DROP",
        "name": "Sudden Density Inversion Fog Flash Collapse",
        "category": "stress_fog",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1, minutes=30)).isoformat(),
        "end_time": (base_time + timedelta(hours=4, minutes=30)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Visibility plummets from 2000m to 250m in 20 minutes. Incoming flights holding.",
        "weather_inputs": {
            "visibility_m": 250.0,
            "rvr_m": 280.0,
            "dewpoint_depression": 0.2,
            "wind_speed_kts": 1.5,
            "cloud_ceiling_ft": 150,
            "is_morning_window": 1.0
        },
        "affected_flight_id": "6E-104",
        "initial_action": "delay",
        "delay_minutes": 75,
        "counter_delay_minutes": 40,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 7,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 172,
        "connecting_pax_count": 28
    })
    annotations.append({
        "scenario_id": "SCEN-04-RAPID-VIS-DROP",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_40m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 42000.0,
        "benchmark_compatibility": True
    })

    # 5. Prolonged fog (8 hours)
    scenarios.append({
        "scenario_id": "SCEN-05-PROLONGED-FOG",
        "name": "Extended 8-Hour Low Visibility Episode",
        "category": "stress_fog",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": base_time.isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Persistent inversion fog trapping BLR basin through noon. Full morning rotation disrupted.",
        "weather_inputs": {
            "visibility_m": 350.0,
            "rvr_m": 320.0,
            "dewpoint_depression": 0.3,
            "wind_speed_kts": 1.0,
            "cloud_ceiling_ft": 200,
            "is_morning_window": 1.0
        },
        "affected_flight_id": "6E-105",
        "initial_action": "excessive_delay",
        "delay_minutes": 280,
        "counter_delay_minutes": 60,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 8,
        "crew_duty_start": (base_time - timedelta(hours=4)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 55
    })
    annotations.append({
        "scenario_id": "SCEN-05-PROLONGED-FOG",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "cancel_flight",
        "known_feasible_alternatives": ["cancel_flight", "swap_tail_with_reserve"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 110000.0,
        "benchmark_compatibility": True
    })

    # 6. Multiple delayed inbound flights
    scenarios.append({
        "scenario_id": "SCEN-06-MULTI-INBOUND-DELAY",
        "name": "Multiple Delayed Inbound Flights Arriving Concurrently",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=3)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Three inbound aircraft from DEL, CCU, and BOM delayed, bunching into same 30m window.",
        "weather_inputs": {"visibility_m": 550.0, "rvr_m": 500.0, "dewpoint_depression": 0.5, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 300, "is_morning_window": 1.0},
        "affected_flight_id": "6E-106",
        "initial_action": "delay",
        "delay_minutes": 50,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 10,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 165,
        "connecting_pax_count": 40
    })
    annotations.append({
        "scenario_id": "SCEN-06-MULTI-INBOUND-DELAY",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_30m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 35000.0,
        "benchmark_compatibility": True
    })

    # 7. Aircraft rotation conflicts
    scenarios.append({
        "scenario_id": "SCEN-07-ROTATION-CONFLICT",
        "name": "Downstream Multi-Sector Rotation Chain Disruption",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Tail VT-BLR01 delayed on Leg 1, jeopardizing 3 subsequent sectors across South network.",
        "weather_inputs": {"visibility_m": 600.0, "rvr_m": 550.0, "dewpoint_depression": 0.6, "wind_speed_kts": 4.0, "cloud_ceiling_ft": 350, "is_morning_window": 1.0},
        "affected_flight_id": "6E-107",
        "initial_action": "swap_tail",
        "delay_minutes": 30,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 12,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 170,
        "connecting_pax_count": 30
    })
    annotations.append({
        "scenario_id": "SCEN-07-ROTATION-CONFLICT",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 8. Tight turnaround constraints
    scenarios.append({
        "scenario_id": "SCEN-08-TIGHT-TURNAROUND",
        "name": "Turnaround Buffer Compression Below Mandatory 35 Minutes",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=4)).isoformat(),
        "end_time": (base_time + timedelta(hours=7)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Inbound delay compresses turnaround to 18m. DGCA safety requires minimum 35m.",
        "weather_inputs": {"visibility_m": 700.0, "rvr_m": 650.0, "dewpoint_depression": 0.7, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 400, "is_morning_window": 1.0},
        "affected_flight_id": "6E-108",
        "initial_action": "delay",
        "delay_minutes": 35,
        "counter_delay_minutes": 35,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 14,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 160,
        "connecting_pax_count": 15
    })
    annotations.append({
        "scenario_id": "SCEN-08-TIGHT-TURNAROUND",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_35m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 20000.0,
        "benchmark_compatibility": True
    })

    # 9. Aircraft maintenance restrictions (AOG)
    scenarios.append({
        "scenario_id": "SCEN-09-AOG-HYDRAULIC-SNAG",
        "name": "Unscheduled Hydraulic Valve Failure (AOG at Hub)",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "disruption_type": "aog",
        "disruption_description": "VT-BLR03 grounded with hydraulic valve failure requiring 6h hangar repair.",
        "weather_inputs": {"visibility_m": 1500.0, "rvr_m": 1500.0, "dewpoint_depression": 2.5, "wind_speed_kts": 5.0, "cloud_ceiling_ft": 1000, "is_morning_window": 1.0},
        "affected_flight_id": "6E-109",
        "initial_action": "swap_tail",
        "delay_minutes": 0,
        "counter_delay_minutes": 20,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 20,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 178,
        "connecting_pax_count": 25
    })
    annotations.append({
        "scenario_id": "SCEN-09-AOG-HYDRAULIC-SNAG",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 10. Crew duty-time constraints (FDP limit)
    scenarios.append({
        "scenario_id": "SCEN-10-CREW-DUTY-MAX-FDP",
        "name": "Cumulative Sector Delay Pushing Crew Against Statutory FDP",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=4)).isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "disruption_type": "crew",
        "disruption_description": "Operating crew has flown 3 sectors. Delay of 60m causes FDP to breach 12.5h maximum.",
        "weather_inputs": {"visibility_m": 600.0, "rvr_m": 550.0, "dewpoint_depression": 0.5, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 300, "is_morning_window": 1.0},
        "affected_flight_id": "6E-110",
        "initial_action": "excessive_delay",
        "delay_minutes": 120,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 14,
        "crew_duty_start": (base_time - timedelta(hours=6, minutes=30)).isoformat(),
        "passenger_count": 175,
        "connecting_pax_count": 32
    })
    annotations.append({
        "scenario_id": "SCEN-10-CREW-DUTY-MAX-FDP",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "swap_standby_crew",
        "known_feasible_alternatives": ["swap_VT-BLR15", "assign_reserve_crew"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 35000.0,
        "benchmark_compatibility": True
    })

    # 11. Crew nearing maximum permissible duty time (WOCL encroachment)
    scenarios.append({
        "scenario_id": "SCEN-11-CREW-WOCL-ENCROACHMENT",
        "name": "Late Night Departure Encroaching Window of Circadian Low (02:00-06:00)",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=18)).isoformat(),
        "end_time": (base_time + timedelta(hours=22)).isoformat(),
        "disruption_type": "crew",
        "disruption_description": "Delayed flight encroaches 02:00-06:00 WOCL window, cutting max permitted FDP to 11.0h.",
        "weather_inputs": {"visibility_m": 900.0, "rvr_m": 850.0, "dewpoint_depression": 0.9, "wind_speed_kts": 4.0, "cloud_ceiling_ft": 500, "is_morning_window": 0.0},
        "affected_flight_id": "6E-111",
        "initial_action": "excessive_delay",
        "delay_minutes": 180,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 16,
        "crew_duty_start": (base_time + timedelta(hours=14)).isoformat(),
        "passenger_count": 168,
        "connecting_pax_count": 18
    })
    annotations.append({
        "scenario_id": "SCEN-11-CREW-WOCL-ENCROACHMENT",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "calibrated_minor_delay",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_30m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 45000.0,
        "benchmark_compatibility": True
    })

    # 12. Airport-slot restrictions
    scenarios.append({
        "scenario_id": "SCEN-12-SLOT-CAPACITY-CRUNCH",
        "name": "Severe Hub Slot Window Oversubscription During Single Runway Operations",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "slot",
        "disruption_description": "Scheduled movements (16) exceed reduced single-runway slot capacity (8).",
        "weather_inputs": {"visibility_m": 400.0, "rvr_m": 350.0, "dewpoint_depression": 0.3, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 200, "is_morning_window": 1.0},
        "affected_flight_id": "6E-112",
        "initial_action": "excessive_delay",
        "delay_minutes": 150,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 4,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 176,
        "connecting_pax_count": 30
    })
    annotations.append({
        "scenario_id": "SCEN-12-SLOT-CAPACITY-CRUNCH",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "cancel_or_swap",
        "known_feasible_alternatives": ["swap_VT-BLR15", "cancel_flight"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 65000.0,
        "benchmark_compatibility": True
    })

    # 13. Night-curfew conflicts
    scenarios.append({
        "scenario_id": "SCEN-13-DELHI-NIGHT-CURFEW",
        "name": "Evening VIDP Night Curfew Breach Threat",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VIDP",
        "start_time": (base_time + timedelta(hours=14)).isoformat(),
        "end_time": (base_time + timedelta(hours=18)).isoformat(),
        "disruption_type": "slot",
        "disruption_description": "Flight from BLR to DEL delayed; arrival projected past DEL mandatory 23:30 runway curfew.",
        "weather_inputs": {"visibility_m": 800.0, "rvr_m": 700.0, "dewpoint_depression": 0.9, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 500, "is_morning_window": 0.0},
        "affected_flight_id": "6E-113",
        "initial_action": "delay",
        "delay_minutes": 140,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 12,
        "crew_duty_start": (base_time + timedelta(hours=10)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 22
    })
    annotations.append({
        "scenario_id": "SCEN-13-DELHI-NIGHT-CURFEW",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "swap_standby_aircraft_depart_on_time",
        "known_feasible_alternatives": ["swap_VT-BLR15", "cancel_flight"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 28000.0,
        "benchmark_compatibility": True
    })

    # 14. Multiple connecting passengers
    scenarios.append({
        "scenario_id": "SCEN-14-CONNECTING-PAX-WAVE",
        "name": "Hub Wave with 85 International & Spoke Connections",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=3)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Inbound flight carries 85 passengers connecting to outbound wave. Holding delay will sever 60 connections.",
        "weather_inputs": {"visibility_m": 500.0, "rvr_m": 450.0, "dewpoint_depression": 0.4, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 250, "is_morning_window": 1.0},
        "affected_flight_id": "6E-114",
        "initial_action": "delay",
        "delay_minutes": 55,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 11,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 85
    })
    annotations.append({
        "scenario_id": "SCEN-14-CONNECTING-PAX-WAVE",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 15. High passenger connection impact
    scenarios.append({
        "scenario_id": "SCEN-15-HIGH-VALUE-PAX-IMPACT",
        "name": "High Passenger Disruption with Multi-Tier Rebooking Liabilities",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Severe passenger care liability if flight is cancelled (DGCA CAR Section 3 hotel mandate).",
        "weather_inputs": {"visibility_m": 450.0, "rvr_m": 400.0, "dewpoint_depression": 0.3, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 200, "is_morning_window": 1.0},
        "affected_flight_id": "6E-115",
        "initial_action": "delay",
        "delay_minutes": 45,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 10,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 70
    })
    annotations.append({
        "scenario_id": "SCEN-15-HIGH-VALUE-PAX-IMPACT",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_30m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 18000.0,
        "benchmark_compatibility": True
    })

    # 16. High-cost cancellation alternatives
    scenarios.append({
        "scenario_id": "SCEN-16-HIGH-COST-CANCELLATION",
        "name": "Cancellation versus Swap Financial Trade-off",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=3)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Cancellation triggers INR 450,000 compensation & hotel liability; tactical swap costs only INR 25,000.",
        "weather_inputs": {"visibility_m": 500.0, "rvr_m": 450.0, "dewpoint_depression": 0.4, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 300, "is_morning_window": 1.0},
        "affected_flight_id": "6E-116",
        "initial_action": "swap_tail",
        "delay_minutes": 0,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 12,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 178,
        "connecting_pax_count": 45
    })
    annotations.append({
        "scenario_id": "SCEN-16-HIGH-COST-CANCELLATION",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 17. Aircraft reassignment opportunities
    scenarios.append({
        "scenario_id": "SCEN-17-STANDBY-TAIL-SWAP",
        "name": "Seamless Standby Aircraft Reassignment at Kempegowda Hub",
        "category": "operational_conflict",
        "severity": "LOW",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=4)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Hot spare VT-BLR15 idle at BLR gate 24. Instant substitution avoids any departure delay.",
        "weather_inputs": {"visibility_m": 800.0, "rvr_m": 750.0, "dewpoint_depression": 0.8, "wind_speed_kts": 4.0, "cloud_ceiling_ft": 450, "is_morning_window": 1.0},
        "affected_flight_id": "6E-117",
        "initial_action": "swap_tail",
        "delay_minutes": 0,
        "counter_delay_minutes": 15,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 16,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 170,
        "connecting_pax_count": 20
    })
    annotations.append({
        "scenario_id": "SCEN-17-STANDBY-TAIL-SWAP",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 18. Simultaneous disruptions across several flights
    scenarios.append({
        "scenario_id": "SCEN-18-SIMULTANEOUS-MULTI-FLIGHT",
        "name": "Simultaneous Multi-Flight Hub Disruption",
        "category": "operational_conflict",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Four flights simultaneously delayed by fog bank. Single standby tail must be prioritized.",
        "weather_inputs": {"visibility_m": 350.0, "rvr_m": 300.0, "dewpoint_depression": 0.2, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 150, "is_morning_window": 1.0},
        "affected_flight_id": "6E-118",
        "initial_action": "delay",
        "delay_minutes": 60,
        "counter_delay_minutes": 35,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 8,
        "crew_duty_start": (base_time - timedelta(hours=3)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 60
    })
    annotations.append({
        "scenario_id": "SCEN-18-SIMULTANEOUS-MULTI-FLIGHT",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_35m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 48000.0,
        "benchmark_compatibility": True
    })

    # 19. Competing recovery plans with different trade-offs
    scenarios.append({
        "scenario_id": "SCEN-19-COMPETING-TRADE-OFFS",
        "name": "Competing Trade-offs: Delay vs Reassignment vs Cancellation",
        "category": "operational_conflict",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=3)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Plan A minimizes cost but misses 40 pax connections; Plan B protects pax but consumes standby aircraft.",
        "weather_inputs": {"visibility_m": 500.0, "rvr_m": 450.0, "dewpoint_depression": 0.4, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 250, "is_morning_window": 1.0},
        "affected_flight_id": "6E-119",
        "initial_action": "delay",
        "delay_minutes": 40,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 10,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 172,
        "connecting_pax_count": 42
    })
    annotations.append({
        "scenario_id": "SCEN-19-COMPETING-TRADE-OFFS",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_25m"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 22000.0,
        "benchmark_compatibility": True
    })

    # 20. Resource-constrained recovery (zero standby fleet)
    scenarios.append({
        "scenario_id": "SCEN-20-ZERO-STANDBY-FLEET",
        "name": "Exhausted Standby Fleet with Zero Spare Aircraft",
        "category": "stress_fog",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=7)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "All 15 aircraft committed in flight. No spare tails. Recovery must rely purely on retiming.",
        "weather_inputs": {"visibility_m": 400.0, "rvr_m": 350.0, "dewpoint_depression": 0.3, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 200, "is_morning_window": 1.0},
        "affected_flight_id": "6E-120",
        "initial_action": "delay",
        "delay_minutes": 45,
        "counter_delay_minutes": 35,
        "candidate_tail": None,
        "no_standby_aircraft": True,
        "slot_capacity": 9,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 165,
        "connecting_pax_count": 24
    })
    annotations.append({
        "scenario_id": "SCEN-20-ZERO-STANDBY-FLEET",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS",
        "expected_best_action": "delay_35m",
        "known_feasible_alternatives": ["delay_35m", "cancel_flight"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 42000.0,
        "benchmark_compatibility": True
    })

    # 21. Cascading delays
    scenarios.append({
        "scenario_id": "SCEN-21-CASCADING-SECTOR-DELAYS",
        "name": "Snowballing Delays Across Multi-Sector Turnarounds",
        "category": "stress_fog",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "disruption_type": "fog",
        "disruption_description": "Initial 45m fog delay snowballs into 160m total delay across 4 consecutive flight legs.",
        "weather_inputs": {"visibility_m": 350.0, "rvr_m": 300.0, "dewpoint_depression": 0.2, "wind_speed_kts": 1.5, "cloud_ceiling_ft": 150, "is_morning_window": 1.0},
        "affected_flight_id": "6E-121",
        "initial_action": "excessive_delay",
        "delay_minutes": 160,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 7,
        "crew_duty_start": (base_time - timedelta(hours=3)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 52
    })
    annotations.append({
        "scenario_id": "SCEN-21-CASCADING-SECTOR-DELAYS",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "PASS_AFTER_COUNTER_PROPOSAL",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": None,
        "solver_optimal_cost_inr": 25000.0,
        "benchmark_compatibility": True
    })

    # --- 6 EXPLICITLY ADVERSARIAL SCENARIOS ---

    # 22. Conflicting operational information [Adversarial 1]
    scenarios.append({
        "scenario_id": "SCEN-22-ADV-CONFLICTING-METAR",
        "name": "Contradictory Weather Observations: METAR 200m RVR vs CAVOK TAF",
        "category": "adversarial",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=4)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "METAR sensor reports RVR 200m (CAT III), but TAF forecast indicates CAVOK 3000m. System must detect conflict and take safe conservative stance.",
        "weather_inputs": {
            "visibility_m": 200.0,
            "rvr_m": 220.0,
            "dewpoint_depression": 0.1,
            "wind_speed_kts": 1.0,
            "cloud_ceiling_ft": 100,
            "is_morning_window": 1.0,
            "conflicting_taf": "CAVOK"
        },
        "affected_flight_id": "6E-122",
        "initial_action": "delay",
        "delay_minutes": 45,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 6,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 170,
        "connecting_pax_count": 25
    })
    annotations.append({
        "scenario_id": "SCEN-22-ADV-CONFLICTING-METAR",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "CONSERVATIVE_SAFETY_STANCE",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": "Conservative sensor-grounded adherence to METAR",
        "solver_optimal_cost_inr": 25000.0,
        "benchmark_compatibility": True
    })

    # 23. Missing weather observations [Adversarial 2]
    scenarios.append({
        "scenario_id": "SCEN-23-ADV-MISSING-WEATHER",
        "name": "Missing Weather Observations: Null Visibility and Sensor Telemetry Dropout",
        "category": "adversarial",
        "severity": "MODERATE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=4)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "AWOS automated station telemetry drops packets: visibility and RVR are None/NaN.",
        "weather_inputs": {
            "visibility_m": 1200.0, # Imputed fallback
            "rvr_m": 1200.0,
            "dewpoint_depression": 1.5,
            "wind_speed_kts": 3.0,
            "cloud_ceiling_ft": 800,
            "is_morning_window": 1.0,
            "is_corrupt_observation": True
        },
        "affected_flight_id": "6E-123",
        "initial_action": "delay",
        "delay_minutes": 30,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 14,
        "crew_duty_start": (base_time - timedelta(hours=1)).isoformat(),
        "passenger_count": 160,
        "connecting_pax_count": 15
    })
    annotations.append({
        "scenario_id": "SCEN-23-ADV-MISSING-WEATHER",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "ROBUST_IMPUTATION_SAFE_EXECUTION",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15", "delay_25m"],
        "expected_failure_or_abstention": "Handled via defensive default imputation",
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 24. Missing or incomplete crew information [Adversarial 3]
    scenarios.append({
        "scenario_id": "SCEN-24-ADV-CORRUPT-CREW-DATA",
        "name": "Missing Crew Duty Record: Unindexed Duty Start Timestamp",
        "category": "adversarial",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "Roster database returns null duty start timestamp for First Officer. System must not hallucinate rest.",
        "weather_inputs": {"visibility_m": 600.0, "rvr_m": 550.0, "dewpoint_depression": 0.5, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 300, "is_morning_window": 1.0},
        "affected_flight_id": "6E-124",
        "initial_action": "delay",
        "delay_minutes": 40,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 12,
        "crew_duty_start": None, # Corrupt/missing
        "passenger_count": 165,
        "connecting_pax_count": 20
    })
    annotations.append({
        "scenario_id": "SCEN-24-ADV-CORRUPT-CREW-DATA",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "DEFENSIVE_DEFAULT_REST_APPLIED",
        "expected_best_action": "swap_standby_crew",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": "Defensive 4-hour default duty assumed to avoid illegal dispatch",
        "solver_optimal_cost_inr": 25000.0,
        "benchmark_compatibility": True
    })

    # 25. Proposed plan violating hard constraint [Adversarial 4]
    scenarios.append({
        "scenario_id": "SCEN-25-ADV-ILLEGAL-PLAN-INJECTION",
        "name": "Adversarial Injection of Legally Defiant Recovery Plan",
        "category": "adversarial",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "Proposal intentionally extends flight past 16h FDP. Crew Legality MUST issue hard veto.",
        "weather_inputs": {"visibility_m": 300.0, "rvr_m": 280.0, "dewpoint_depression": 0.2, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 150, "is_morning_window": 1.0},
        "affected_flight_id": "6E-125",
        "initial_action": "excessive_delay",
        "delay_minutes": 420, # Blatant 7-hour delay breaching all FDTL limits
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 6,
        "crew_duty_start": (base_time - timedelta(hours=12)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 45
    })
    annotations.append({
        "scenario_id": "SCEN-25-ADV-ILLEGAL-PLAN-INJECTION",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "HARD_VETO_ENFORCED",
        "expected_best_action": "counter_proposal_swap_or_cancel",
        "known_feasible_alternatives": ["swap_VT-BLR15", "cancel_flight"],
        "expected_failure_or_abstention": "Initial illegal proposal strictly vetoed; counter-proposal approved",
        "solver_optimal_cost_inr": 20000.0,
        "benchmark_compatibility": True
    })

    # 26. Misleading low-cost plan creating severe passenger impact [Adversarial 5]
    scenarios.append({
        "scenario_id": "SCEN-26-ADV-MISLEADING-LOW-COST",
        "name": "Deceptive Low-Cost Plan Masking Massive Passenger Care Liabilities",
        "category": "adversarial",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=2)).isoformat(),
        "end_time": (base_time + timedelta(hours=6)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "A plan with near-zero fuel cost cancels flight outright, but strands 180 passengers overnight at remote station. Multi-objective scoring must penalize.",
        "weather_inputs": {"visibility_m": 500.0, "rvr_m": 450.0, "dewpoint_depression": 0.4, "wind_speed_kts": 3.0, "cloud_ceiling_ft": 250, "is_morning_window": 1.0},
        "affected_flight_id": "6E-126",
        "initial_action": "delay",
        "delay_minutes": 40,
        "counter_delay_minutes": 25,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 10,
        "crew_duty_start": (base_time - timedelta(hours=2)).isoformat(),
        "passenger_count": 180,
        "connecting_pax_count": 80
    })
    annotations.append({
        "scenario_id": "SCEN-26-ADV-MISLEADING-LOW-COST",
        "expected_feasibility": True,
        "expected_hard_constraint_outcome": "MULTI_OBJECTIVE_PENALTY_PENALIZATION",
        "expected_best_action": "swap_VT-BLR15",
        "known_feasible_alternatives": ["swap_VT-BLR15"],
        "expected_failure_or_abstention": "Cost agent flags massive DGCA CAR Section 3 hotel penalty, rejecting pure cancellation",
        "solver_optimal_cost_inr": 15000.0,
        "benchmark_compatibility": True
    })

    # 27. Ambiguous split-duty FDTL regulation forcing abstention [Adversarial 6]
    scenarios.append({
        "scenario_id": "SCEN-27-ADV-AMBIGUOUS-FDTL-ABSTAIN",
        "name": "Unindexed Fringe Statutory Rule Forcing Human Escalation & Abstention",
        "category": "adversarial",
        "severity": "SEVERE",
        "airport": "VOBL",
        "start_time": (base_time + timedelta(hours=1)).isoformat(),
        "end_time": (base_time + timedelta(hours=5)).isoformat(),
        "disruption_type": "adversarial",
        "disruption_description": "Pilot started duty at 01:55 AM on border of WOCL split-duty extension. Ambiguous regulatory precedent forces Agentic RAG to safely abstain.",
        "weather_inputs": {"visibility_m": 350.0, "rvr_m": 300.0, "dewpoint_depression": 0.2, "wind_speed_kts": 2.0, "cloud_ceiling_ft": 180, "is_morning_window": 1.0},
        "affected_flight_id": "6E-127",
        "initial_action": "excessive_delay",
        "delay_minutes": 200,
        "counter_delay_minutes": 30,
        "candidate_tail": "VT-BLR15",
        "slot_capacity": 6,
        "crew_duty_start": (base_time - timedelta(hours=3, minutes=5)).isoformat(),
        "passenger_count": 175,
        "connecting_pax_count": 35,
        "trigger_abstention": True
    })
    annotations.append({
        "scenario_id": "SCEN-27-ADV-AMBIGUOUS-FDTL-ABSTAIN",
        "expected_feasibility": False,
        "expected_hard_constraint_outcome": "SAFE_ABSTENTION_AND_ESCALATION",
        "expected_best_action": "escalate_to_human_duty_manager",
        "known_feasible_alternatives": [],
        "expected_failure_or_abstention": "Crew Legality ABSTAINED due to ambiguous statutory boundary; Mediator escalates to Human Duty Manager",
        "solver_optimal_cost_inr": 0.0,
        "benchmark_compatibility": False
    })

    return {
        "metadata": {
            "version": "2.0.0",
            "hub_airport": "VOBL",
            "total_scenarios": len(scenarios),
            "standard_and_stress_count": 21,
            "adversarial_count": 6,
            "provenance": {
                "weather": "NOAA / IMD Kempegowda VOBL METAR Archives (5736 half-hourly records)",
                "flight_operations": "Synthetic schedule calibrated against BTS / DGCA domestic A320 block hours",
                "crew_regulations": "DGCA CAR Section 7, Series J, Part III (2019 baseline with 2024 revision toggle)",
                "passenger_mandates": "DGCA CAR Section 3, Series M, Part IV passenger rights"
            }
        },
        "scenarios": scenarios,
        "annotations": annotations
    }


def main():
    dataset = generate_evaluation_dataset()
    base_dir = Path(__file__).resolve().parent

    scen_file = base_dir / "scenarios.json"
    annot_file = base_dir / "scenario_annotations.json"

    with open(scen_file, "w", encoding="utf-8") as f:
        json.dump(dataset["scenarios"], f, indent=2)

    with open(annot_file, "w", encoding="utf-8") as f:
        json.dump(dataset["annotations"], f, indent=2)

    print(f"Generated {len(dataset['scenarios'])} scenarios in {scen_file}")
    print(f"Generated {len(dataset['annotations'])} ground truth annotations in {annot_file}")


if __name__ == "__main__":
    main()

