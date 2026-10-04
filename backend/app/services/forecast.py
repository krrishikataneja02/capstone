"""
Predictive analytics — Random Forest regression on calendar features.

Pure function: list[dict] in → predictions + MAE out.  No DB / API dependency.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _extract_features(ts: datetime) -> list[float]:
    """Return [hour, weekday, is_weekend, sin_hour, cos_hour]."""
    hour = ts.hour + ts.minute / 60.0
    weekday = ts.weekday()
    is_weekend = 1.0 if weekday >= 5 else 0.0
    sin_hour = math.sin(2 * math.pi * hour / 24)
    cos_hour = math.cos(2 * math.pi * hour / 24)
    return [hour, weekday, is_weekend, sin_hour, cos_hour]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def train_and_predict(
    records: list[dict],
    n_future: int = 24,
    last_ts: datetime | None = None,
) -> dict:
    """
    Train a Random Forest on historical records and predict *n_future* hours.

    Parameters
    ----------
    records : list of ``{"ts": datetime, "value": float}``
    n_future : how many hourly predictions to produce
    last_ts : starting point for the forecast window (default: max ts in data)

    Returns
    -------
    dict with keys ``predictions``, ``mae``, ``model_name``
    """
    if len(records) < 10:
        raise ValueError("Need at least 10 data points for training")
    if n_future < 1:
        raise ValueError("n_future must be at least 1")
    if any(
        not isinstance(record.get("ts"), datetime)
        or not isinstance(record.get("value"), (int, float))
        or not math.isfinite(record["value"])
        for record in records
    ):
        raise ValueError("Records must contain datetime timestamps and finite numeric values")

    X = np.array([_extract_features(r["ts"]) for r in records])
    y = np.array([r["value"] for r in records])

    # ---------- holdout MAE ----------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    mae = float(np.mean(np.abs(y_test - model.predict(X_test))))

    # ---------- retrain on full data ----------
    model.fit(X, y)

    # ---------- forecast ----------
    if last_ts is None:
        last_ts = max(r["ts"] for r in records)

    predictions: list[dict] = []
    for i in range(1, n_future + 1):
        future_ts = last_ts + timedelta(hours=i)
        feat = np.array([_extract_features(future_ts)])
        pred_val = float(model.predict(feat)[0])
        predictions.append(
            {"ts": future_ts.isoformat(), "value": round(max(0.0, pred_val), 4)}
        )

    return {
        "predictions": predictions,
        "mae": round(mae, 4),
        "model_name": "RandomForestRegressor",
    }
