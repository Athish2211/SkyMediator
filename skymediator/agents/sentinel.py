"""
Sentinel Agent — Disruption Prediction and Early Warning.
Trains and executes a scikit-learn classification model on METAR weather observations
to predict winter radiation fog onset and lead time for Kempegowda Hub (VOBL).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from skymediator.config import settings
from skymediator.ingest.fetch_weather import generate_synthetic_winter_metar, extract_fog_features
from skymediator.logging_config import TraceSpan, write_trace_span, logger


class SentinelOutput(BaseModel):
    disruption_detected: bool
    event_type: Literal["fog", "aog", "none"] = "fog"
    probability: float = Field(ge=0.0, le=1.0)
    expected_start: Optional[str] = None
    expected_end: Optional[str] = None
    expected_lead_time_hours: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: Literal["monitor", "pre_position", "act_early", "standby"]
    brier_score: Optional[float] = None
    rationale: str


class SentinelAgent:
    """Predictive agent monitoring weather observations to forecast hub disruptions."""

    _MODEL_CACHE: Dict[str, Tuple[Pipeline, float]] = {}

    def __init__(self, airport: str = "VOBL"):
        self.airport = airport
        if airport in SentinelAgent._MODEL_CACHE:
            self.pipeline, self.training_brier_score = SentinelAgent._MODEL_CACHE[airport]
        else:
            self.pipeline = None
            self._train_fog_model()
            if self.pipeline:
                SentinelAgent._MODEL_CACHE[airport] = (self.pipeline, self.training_brier_score)

    def _train_fog_model(self) -> None:
        """Trains a scikit-learn classification pipeline on historical or synthetic winter METAR history."""
        import csv
        historical_csv = settings.DATA_DIR / "historical" / f"{self.airport}_METAR_winter_history.csv"
        if historical_csv.exists():
            observations = []
            try:
                with open(historical_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        observations.append({
                            "station": row["station"],
                            "ts": row["ts"],
                            "visibility_m": float(row["visibility_m"]),
                            "rvr_m": float(row["rvr_m"]),
                            "temp_c": float(row["temperature_c"]),
                            "dewpoint_c": float(row["dewpoint_c"]),
                            "dewpoint_depression": float(row["dewpoint_depression"]),
                            "wind_speed_kts": float(row["wind_speed_kts"]),
                            "wind_dir_deg": int(row["wind_dir_deg"]),
                            "cloud_ceiling_ft": int(row["cloud_ceiling_ft"]),
                            "is_morning_window": float(row["is_morning_window"]),
                            "present_weather": ["FG"] if int(row.get("is_fog_event", 0)) else []
                        })
                logger.info(f"Sentinel training on {len(observations)} real historical METAR records for {self.airport}.")
            except Exception as e:
                logger.warning(f"Error loading historical METAR CSV: {e}. Falling back to synthetic.")
                observations = generate_synthetic_winter_metar(station=self.airport, num_hours=168)
        else:
            observations = generate_synthetic_winter_metar(station=self.airport, num_hours=168)
        
        X: List[List[float]] = []
        y: List[int] = []

        for obs in observations:
            feats = extract_fog_features(obs)
            X.append([
                feats["visibility_m"],
                feats["rvr_m"],
                feats["dewpoint_depression"],
                feats["wind_speed_kts"],
                feats["cloud_ceiling_ft"],
                feats["is_morning_window"]
            ])
            # Ground truth: Fog condition when visibility < 600m or RVR < 550m
            label = 1 if (obs["visibility_m"] < 600 or (obs.get("rvr_m") and obs["rvr_m"] < 550)) else 0
            y.append(label)

        X_arr = np.array(X)
        y_arr = np.array(y)

        # Train standard logistic regression classifier
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(random_state=settings.DEFAULT_SEED, max_iter=200))
        ])
        self.pipeline.fit(X_arr, y_arr)

        # Compute training Brier score calibration
        preds = self.pipeline.predict_proba(X_arr)[:, 1]
        self.training_brier_score = float(brier_score_loss(y_arr, preds))
        logger.info(f"Sentinel fog model trained for {self.airport}. Brier score: {self.training_brier_score:.4f}")

    def evaluate_forecast(
        self,
        current_observation: Dict[str, Any],
        run_id: str = "PREDICT"
    ) -> SentinelOutput:
        """Evaluates current weather observation and returns calibrated disruption forecast."""
        if not self.pipeline:
            self._train_fog_model()

        feats = extract_fog_features(current_observation)
        x_vec = np.array([[
            feats["visibility_m"],
            feats["rvr_m"],
            feats["dewpoint_depression"],
            feats["wind_speed_kts"],
            feats["cloud_ceiling_ft"],
            feats["is_morning_window"]
        ]])

        prob = float(self.pipeline.predict_proba(x_vec)[0, 1])
        disruption_detected = prob >= 0.45

        # Estimate lead time and recommended actions
        obs_time = datetime.fromisoformat(current_observation.get("ts", datetime.utcnow().isoformat()))
        lead_time = 3.5 if disruption_detected else 0.0

        if prob >= 0.75:
            rec_action = "act_early"
            rationale = f"High probability ({prob*100:.1f}%) of severe CAT III radiation fog at {self.airport}. Recommend early aircraft swap and crew duty buffer check."
        elif prob >= 0.45:
            rec_action = "pre_position"
            rationale = f"Moderate probability ({prob*100:.1f}%) of fog onset. Recommend pre-positioning reserve crew at hub."
        else:
            rec_action = "monitor"
            rationale = f"Low fog risk ({prob*100:.1f}%). Normal visual flight operations maintained."

        from skymediator.llm import synthesize_sentinel_rationale, is_gemini_available
        if is_gemini_available():
            llm_rat = synthesize_sentinel_rationale(self.airport, prob, current_observation, rec_action)
            if llm_rat and not llm_rat.startswith("[Deterministic"):
                rationale = llm_rat

        output = SentinelOutput(
            disruption_detected=disruption_detected,
            event_type="fog" if disruption_detected else "none",
            probability=round(prob, 3),
            expected_start=(obs_time + timedelta(hours=lead_time)).isoformat() if disruption_detected else None,
            expected_end=(obs_time + timedelta(hours=lead_time + 3.0)).isoformat() if disruption_detected else None,
            expected_lead_time_hours=lead_time,
            confidence=round(max(prob, 1.0 - prob), 3),
            recommended_action=rec_action,
            brier_score=round(self.training_brier_score, 4),
            rationale=rationale
        )

        span = TraceSpan(
            span_id=f"SENT-{datetime.utcnow().strftime('%H%M%S')}",
            run_id=run_id,
            round=1,
            agent="Sentinel",
            action_type="AGENT_INVOCATION",
            tool_name="fog_risk_model",
            input_payload=feats,
            output_payload=output.model_dump()
        )
        write_trace_span(span)

        return output
