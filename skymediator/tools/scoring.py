"""
Deterministic multi-objective normalized scoring tool (resolving GAP-06 & PROP-02).
Normalizes delay, passenger disruption, operational cost, and crew buffer penalties to [0, 1].
"""

from typing import Any, Dict, Optional
from skymediator.config import settings


def score_plan(
    delay_minutes: float,
    missed_connections: int,
    total_cost: float,
    crew_buffer_penalty: float = 0.0,
    weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Computes a bounded scalar penalty score in [0.0, 1.0].
    Lower score indicates a superior recovery plan.
    """
    w = weights or settings.SCORING_WEIGHTS

    norm_delay = min(1.0, max(0.0, delay_minutes / settings.NORMALIZATION_CAP_DELAY_MINUTES))
    norm_pax = min(1.0, max(0.0, missed_connections / settings.NORMALIZATION_CAP_MISSED_PAX))
    norm_cost = min(1.0, max(0.0, total_cost / settings.NORMALIZATION_CAP_COST))
    norm_crew = min(1.0, max(0.0, crew_buffer_penalty / settings.NORMALIZATION_CAP_CREW_BUFFER))

    composite_penalty = (
        w.get("delay", 0.30) * norm_delay +
        w.get("pax", 0.30) * norm_pax +
        w.get("cost", 0.30) * norm_cost +
        w.get("crew", 0.10) * norm_crew
    )

    return {
        "composite_score": round(composite_penalty, 4),
        "normalized_components": {
            "delay": round(norm_delay, 4),
            "pax": round(norm_pax, 4),
            "cost": round(norm_cost, 4),
            "crew": round(norm_crew, 4),
        },
        "raw_inputs": {
            "delay_minutes": delay_minutes,
            "missed_connections": missed_connections,
            "total_cost": total_cost,
            "crew_buffer_penalty": crew_buffer_penalty
        }
    }
