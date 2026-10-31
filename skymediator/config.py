"""
Configuration and runtime settings for SkyMediator.
Validated via Pydantic Settings.
"""

import os
from pathlib import Path
from typing import Literal, Dict, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Auto-load .env file into os.environ
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)
    try:
        # Also manually load to ensure compatibility
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k = _k.strip()
                    _v = _v.strip().strip('"').strip("'")
                    if _k not in os.environ:
                        os.environ[_k] = _v
    except Exception as e:
        print(f"Warning: Failed to load .env file: {e}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKYMEDIATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Operational Scope
    HUB_AIRPORT: str = Field(default="VOBL", description="ICAO code for primary hub (Bengaluru Kempegowda International)")
    HUB_IATA: str = Field(default="BLR", description="IATA code for primary hub")
    TIMEZONE: str = Field(default="Asia/Kolkata", description="Primary operational timezone")
    DEFAULT_SEED: int = Field(default=42, description="Pseudo-random seed for deterministic fixtures")
    
    # Regulations
    FDTL_VERSION: Literal["2019", "2024"] = Field(
        default="2019", 
        description="DGCA CAR Section 7, Series J, Part III regulatory standard baseline"
    )

    # LLM Settings
    GEMINI_API_KEY: Optional[str] = Field(
        default_factory=lambda: os.environ.get("SKYMEDIATOR_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        description="Google Gemini API key for natural language rationale & RAG reformulation"
    )
    LLM_MODEL: str = Field(
        default="gemini-flash-lite-latest",
        description="Google Gemini model name (e.g. gemini-flash-lite-latest)"
    )

    # Orchestration Boundaries
    MAX_NEGOTIATION_ROUNDS: int = Field(default=3, description="Hard upper bound on multi-agent negotiation rounds")
    SCORE_IMPROVEMENT_THRESHOLD: float = Field(default=0.01, description="Minimum score improvement delta for convergence")
    ESCALATION_DIFF_MARGIN: float = Field(default=0.05, description="Margin of score difference triggering mandatory escalation")
    
    # Normalization Caps for Multi-Objective Scoring
    NORMALIZATION_CAP_DELAY_MINUTES: float = Field(default=600.0, description="Max delay normalization benchmark")
    NORMALIZATION_CAP_MISSED_PAX: float = Field(default=200.0, description="Max missed pax normalization benchmark")
    NORMALIZATION_CAP_COST: float = Field(default=1_000_000.0, description="Max financial cost benchmark in INR")
    NORMALIZATION_CAP_CREW_BUFFER: float = Field(default=120.0, description="Max crew buffer penalty in minutes")

    # Scoring Weights (sum = 1.0)
    SCORING_WEIGHTS: Dict[str, float] = Field(
        default_factory=lambda: {
            "delay": 0.30,
            "pax": 0.30,
            "cost": 0.30,
            "crew": 0.10,
        }
    )

    # Paths
    BASE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    DATA_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    DB_PATH: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "processed" / "skymediator.db")
    TRACES_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "traces")
    LOG_LEVEL: str = Field(default="INFO")


# Global singleton settings instance
settings = Settings()
