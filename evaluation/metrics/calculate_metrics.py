"""
Deterministic Metric Calculation Engine for SkyMediator Evaluation.
Computes prediction metrics, operational recovery metrics, constraint compliance,
and agentic deliberation overhead without LLM arithmetic.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, precision_recall_curve, auc, confusion_matrix,
    brier_score_loss, roc_curve
)
from sklearn.calibration import calibration_curve

from skymediator.eval.validator_fdtl import validate_plan_independent
from skymediator.tools.slots import check_slot
from skymediator.tools.schedule import apply_plan_diff


def compute_sentinel_prediction_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.45
) -> Dict[str, Any]:
    """Computes comprehensive classification, calibration, and curve metrics for Sentinel."""
    y_pred = (y_prob >= threshold).astype(int)

    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    brier = float(brier_score_loss(y_true, y_prob))

    try:
        roc_auc = float(roc_auc_score(y_true, y_prob))
    except Exception:
        roc_auc = 0.5

    fpr, tpr, roc_thresholds = roc_curve(y_true, y_prob)
    pr_prec, pr_rec, pr_thresholds = precision_recall_curve(y_true, y_prob)
    pr_auc = float(auc(pr_rec, pr_prec))

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)

    # Reliability diagram calibration curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=10, strategy="uniform")

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "brier_score": brier,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp)
        },
        "roc_curve": {
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist()
        },
        "pr_curve": {
            "precision": pr_prec.tolist(),
            "recall": pr_rec.tolist()
        },
        "calibration": {
            "prob_true": prob_true.tolist(),
            "prob_pred": prob_pred.tolist()
        }
    }


def evaluate_plan_compliance_and_cost(
    candidate_plan: Dict[str, Any],
    base_schedule: List[Dict[str, Any]],
    crew_roster: List[Dict[str, Any]],
    slot_windows: List[Dict[str, Any]],
    fdtl_version: str = "2019_baseline"
) -> Dict[str, Any]:
    """
    Applies candidate plan mutations and verifies:
    1. Independent clean-room FDTL validator (Gate 5)
    2. Deterministic airport slot movement capacity
    3. Operational cost and passenger care liability
    """
    plan_diff = candidate_plan.get("plan_diff", [])
    mutated_res = apply_plan_diff(base_schedule, plan_diff)
    mutated_schedule = mutated_res["mutated_flights"]

    # 1. Independent Clean-Room FDTL Validation
    fdtl_res = validate_plan_independent(
        mutated_schedule=mutated_schedule,
        crew_rosters=crew_roster
    )
    is_fdtl_legal = fdtl_res.get("is_compliant", len(fdtl_res.get("violations", [])) == 0)
    fdtl_violations_count = fdtl_res.get("violation_count", len(fdtl_res.get("violations", [])))

    # 2. Slot Validation
    hub = base_schedule[0]["origin"] if base_schedule else "VOBL"
    slot_res = check_slot(hub, mutated_schedule, slot_windows)
    is_slot_valid = slot_res["is_valid"]
    slot_violations_count = len(slot_res["violated_windows"])

    # 3. Overall Feasibility
    is_feasible = is_fdtl_legal and is_slot_valid and candidate_plan.get("plan_id") != "ESCALATED"

    # 4. Operational Cost and Delay
    scores = candidate_plan.get("scores") or {}
    raw_metrics = scores.get("raw_metrics") or {}
    total_cost = float(raw_metrics.get("total_cost", 0.0))
    delay_minutes = float(raw_metrics.get("delay_minutes", 0.0))
    pax_disrupted = int(raw_metrics.get("missed_connections", 0)) + int(raw_metrics.get("affected_passengers", 0))
    composite_score = float(scores.get("composite_score", 0.0))

    # Fallback calculation if raw_metrics missing
    if total_cost == 0.0 and delay_minutes == 0.0 and plan_diff:
        for op in plan_diff:
            op_dict = op if isinstance(op, dict) else op.model_dump()
            if op_dict.get("op") == "delay":
                d_m = float(op_dict.get("delay_minutes", 0.0))
                delay_minutes += d_m
                total_cost += d_m * 600.0
            elif op_dict.get("op") == "cancel":
                total_cost += 250000.0
            elif op_dict.get("op") == "swap_tail":
                total_cost += 15000.0

    return {
        "is_feasible": is_feasible,
        "is_fdtl_legal": is_fdtl_legal,
        "fdtl_violations_count": fdtl_violations_count,
        "is_slot_valid": is_slot_valid,
        "slot_violations_count": slot_violations_count,
        "total_cost_inr": total_cost,
        "delay_minutes": delay_minutes,
        "pax_disrupted": pax_disrupted,
        "composite_score": composite_score,
        "mutated_flights_count": len(mutated_schedule)
    }
