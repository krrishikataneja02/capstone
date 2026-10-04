"""
Anomaly detection — Isolation Forest + statistical z-score.

Pure function: observed value + historical window in → anomaly verdict out.
No DB / API dependency.
"""

from __future__ import annotations

import numpy as np
import math
from sklearn.ensemble import IsolationForest


def detect_anomaly(
    observed: float,
    historical_window: list[float],
    contamination: float = 0.05,
    z_threshold: float = 3.0,
) -> dict:
    """
    Flag an anomaly only when **both** conditions are met:

    1. Isolation Forest classifies the observation as an outlier (predict == -1).
    2. The absolute z-score of the observation vs. the window is ≥ *z_threshold*.

    Parameters
    ----------
    observed : the new reading
    historical_window : recent values (≥ 10 recommended)
    contamination : IF contamination parameter
    z_threshold : z-score gate

    Returns
    -------
    dict with ``is_anomaly``, ``score``, ``z_score``, ``expected``
    """
    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be greater than 0 and at most 0.5")
    if not math.isfinite(z_threshold) or z_threshold < 0:
        raise ValueError("z_threshold must be finite and non-negative")

    try:
        observed = float(observed)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("observed must be a finite number") from exc

    finite_window: list[float] = []
    for value in historical_window:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(numeric_value):
            finite_window.append(numeric_value)

    mean = float(np.mean(finite_window)) if finite_window else (observed if math.isfinite(observed) else 0.0)
    if not math.isfinite(observed):
        return {
            "is_anomaly": False,
            "score": 0.0,
            "z_score": 0.0,
            "expected": round(mean, 4),
        }

    if len(finite_window) < 10:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "z_score": 0.0,
            "expected": round(mean, 4),
        }

    window_arr = np.array(finite_window).reshape(-1, 1)
    obs_arr = np.array([[observed]])

    # Isolation Forest
    iso = IsolationForest(
        contamination=contamination, random_state=42, n_estimators=100
    )
    iso.fit(window_arr)
    prediction = int(iso.predict(obs_arr)[0])       # -1 = outlier, 1 = inlier
    raw_score = float(iso.score_samples(obs_arr)[0])  # more negative → more anomalous

    # Z-score
    mean = float(np.mean(finite_window))
    std = float(np.std(finite_window))
    z_score = abs((observed - mean) / std) if std > 0 else 0.0

    is_anomaly = (prediction == -1) and (z_score >= z_threshold)

    return {
        "is_anomaly": is_anomaly,
        "score": round(raw_score, 4),
        "z_score": round(z_score, 4),
        "expected": round(mean, 4),
    }
