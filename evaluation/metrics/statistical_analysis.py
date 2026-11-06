"""
Statistical Analysis and Hypothesis Testing Module for SkyMediator.
Computes:
- Parametric statistics (Mean, Standard Deviation, Cohen's d)
- Non-parametric statistics (Median, Interquartile Range, Cliff's Delta)
- 95% Bootstrap Confidence Intervals (Paired Resampling)
- Wilcoxon Signed-Rank Tests for Paired Comparisons
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats


def compute_summary_statistics(data: List[float]) -> Dict[str, float]:
    """Computes descriptive parametric and non-parametric summary statistics."""
    arr = np.array(data, dtype=float)
    if len(arr) == 0:
        return {"mean": 0.0, "std": 0.0, "median": 0.0, "iqr": 0.0, "q25": 0.0, "q75": 0.0}

    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    med_val = float(np.median(arr))
    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    iqr_val = float(q75 - q25)

    return {
        "mean": round(mean_val, 4),
        "std": round(std_val, 4),
        "median": round(med_val, 4),
        "iqr": round(iqr_val, 4),
        "q25": round(q25, 4),
        "q75": round(q75, 4)
    }


def compute_bootstrap_ci(
    data: List[float],
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    random_seed: int = 42
) -> Tuple[float, float]:
    """Computes two-sided bootstrap confidence intervals for the sample mean."""
    arr = np.array(data, dtype=float)
    if len(arr) <= 1:
        val = float(arr[0]) if len(arr) == 1 else 0.0
        return (val, val)

    rng = np.random.default_rng(random_seed)
    resamples = rng.choice(arr, size=(n_resamples, len(arr)), replace=True)
    resample_means = np.mean(resamples, axis=1)

    lower_pct = ((1.0 - confidence_level) / 2.0) * 100.0
    upper_pct = (confidence_level + (1.0 - confidence_level) / 2.0) * 100.0

    ci_lower = float(np.percentile(resample_means, lower_pct))
    ci_upper = float(np.percentile(resample_means, upper_pct))

    return (round(ci_lower, 4), round(ci_upper, 4))


def compute_paired_comparison(
    treatment: List[float],
    control: List[float],
    n_resamples: int = 1000,
    random_seed: int = 42
) -> Dict[str, Any]:
    """
    Performs paired statistical analysis between two configurations:
    1. Paired difference summary
    2. 95% Bootstrap CI of paired difference
    3. Wilcoxon signed-rank test
    4. Cliff's Delta and Rank-Biserial effect size
    """
    t_arr = np.array(treatment, dtype=float)
    c_arr = np.array(control, dtype=float)
    n = min(len(t_arr), len(c_arr))

    if n == 0:
        return {"error": "Empty data series"}

    t_arr = t_arr[:n]
    c_arr = c_arr[:n]
    diff = t_arr - c_arr

    # Wilcoxon signed-rank test
    # (handles zero-differences gracefully)
    non_zero_diff = diff[diff != 0]
    if len(non_zero_diff) >= 5:
        try:
            stat, p_value = stats.wilcoxon(t_arr, c_arr)
            stat = float(stat)
            p_val = float(p_value)
        except Exception:
            stat, p_val = 0.0, 1.0
    else:
        stat, p_val = 0.0, 1.0

    # 95% Bootstrap CI on mean paired difference
    rng = np.random.default_rng(random_seed)
    diff_resamples = rng.choice(diff, size=(n_resamples, n), replace=True)
    diff_means = np.mean(diff_resamples, axis=1)
    ci_lower = float(np.percentile(diff_means, 2.5))
    ci_upper = float(np.percentile(diff_means, 97.5))

    # Cliff's Delta (dominance effect size)
    greater = sum(t > c for t in t_arr for c in c_arr)
    lesser = sum(t < c for t in t_arr for c in c_arr)
    total_pairs = len(t_arr) * len(c_arr)
    cliffs_delta = (greater - lesser) / total_pairs if total_pairs > 0 else 0.0

    # Cohen's d (paired)
    std_diff = np.std(diff, ddof=1) if n > 1 else 0.0
    cohens_d = float(np.mean(diff) / std_diff) if std_diff > 0 else 0.0

    return {
        "n_samples": n,
        "mean_treatment": round(float(np.mean(t_arr)), 4),
        "mean_control": round(float(np.mean(c_arr)), 4),
        "mean_difference": round(float(np.mean(diff)), 4),
        "diff_ci_95": [round(ci_lower, 4), round(ci_upper, 4)],
        "wilcoxon_stat": round(stat, 4),
        "p_value": round(p_val, 6),
        "statistically_significant": p_val < 0.05,
        "cliffs_delta": round(float(cliffs_delta), 4),
        "cohens_d": round(cohens_d, 4)
    }

