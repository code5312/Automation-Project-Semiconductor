"""Sensor anomaly scoring for SECOM feature rows.

Fits normal-row (Pass/Fail == -1) statistics once via `fit_sensor_model`,
then scores individual rows against that baseline via `extract_sensor_signal`.
Two scoring methods are available, selected with `method`:

- "topn_zscore": mean |z| of the top-N sensors, squashed into [0, 1).
- "isolation_forest": IsolationForest anomaly score, min-max normalized
  against the full dataset's score range into [0, 1].
"""
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

Method = Literal["topn_zscore", "isolation_forest"]


@dataclass
class SensorModel:
    feature_cols: list[str]
    scaler: StandardScaler
    method: Method
    top_n: int = 5
    iso_forest: Optional[IsolationForest] = None
    iso_score_min: float = 0.0
    iso_score_max: float = 1.0


def fit_sensor_model(
    df: pd.DataFrame,
    feature_cols: list[str],
    method: Method = "topn_zscore",
    top_n: int = 5,
    normal_label_col: str = "Pass/Fail",
    normal_label_value: int = -1,
    random_state: int = 0,
) -> SensorModel:
    normal_df = df[df[normal_label_col] == normal_label_value]
    scaler = StandardScaler().fit(normal_df[feature_cols])

    iso_forest = None
    iso_min, iso_max = 0.0, 1.0
    if method == "isolation_forest":
        z_normal = scaler.transform(normal_df[feature_cols])
        z_all = scaler.transform(df[feature_cols])
        iso_forest = IsolationForest(random_state=random_state, n_estimators=200)
        iso_forest.fit(z_normal)
        raw_scores = -iso_forest.score_samples(z_all)  # higher = more anomalous
        iso_min, iso_max = float(raw_scores.min()), float(raw_scores.max())

    return SensorModel(
        feature_cols=feature_cols,
        scaler=scaler,
        method=method,
        top_n=top_n,
        iso_forest=iso_forest,
        iso_score_min=iso_min,
        iso_score_max=iso_max,
    )


def _row_zscores(model: SensorModel, df: pd.DataFrame, row_idx: int) -> np.ndarray:
    row = df.loc[[row_idx], model.feature_cols]
    return model.scaler.transform(row)[0]


def extract_sensor_signal(model: SensorModel, df: pd.DataFrame, row_idx: int) -> dict:
    z = _row_zscores(model, df, row_idx)
    abs_z = np.abs(z)
    top_idx = np.argsort(abs_z)[::-1][: model.top_n]
    top_sensors = [
        {
            "sensor_id": str(model.feature_cols[i]),
            "z": float(z[i]),
            "unit": "unknown",
            "meaning": "unknown",
        }
        for i in top_idx
    ]

    if model.method == "topn_zscore":
        top_mean = float(np.mean(abs_z[top_idx]))
        anomaly_score = 1.0 - float(np.exp(-top_mean / 3.0))
    elif model.method == "isolation_forest":
        raw = float(-model.iso_forest.score_samples(z.reshape(1, -1))[0])
        span = model.iso_score_max - model.iso_score_min
        anomaly_score = (raw - model.iso_score_min) / span if span > 0 else 0.0
    else:
        raise ValueError(f"Unknown method: {model.method}")

    return {
        "anomaly_score": float(np.clip(anomaly_score, 0.0, 1.0)),
        "top_sensors": top_sensors,
    }


def compute_anomaly_scores_batch(model: SensorModel, df: pd.DataFrame) -> pd.Series:
    """Anomaly score for every row in df, indexed the same as df."""
    scores = {idx: extract_sensor_signal(model, df, idx)["anomaly_score"] for idx in df.index}
    return pd.Series(scores)
