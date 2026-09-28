"""Shared test fixtures: a lightweight, synthetic SamplingContext so tests
(especially the API tests) don't need the real SECOM/vibration/WM-811K
files on disk."""
import numpy as np
import pandas as pd
import pytest

from src.scenarios.catalog import SamplingContext
from src.signals.sensor import compute_anomaly_scores_batch, fit_sensor_model

FAKE_RULES = {
    "weights": {
        "equipment": {"edge_pattern": 0.4, "vibration_abnormal": 0.4, "sensor_normal": 0.2},
        "process": {"center_pattern": 0.3, "sensor_anomaly": 0.5, "vibration_normal": 0.2},
    },
    "thresholds": {
        "hi_cap": 6,
        "hi_normal_max": 1.0,
        "sensor_low": 0.3,
        "score_min": 0.6,
        "score_gap_min": 0.15,
        "kurtosis_baseline": 3.0,
        "kurtosis_cap": 6.0,
        "crest_factor_baseline": 4.0,
        "crest_factor_cap": 8.0,
        "abnormality_low_max": 0.3,
    },
    "depts": {"equipment": "M-ENG", "process": "P-ENG", "unclear": "YI"},
}

FAKE_SCENARIOS = {
    "SC-EQ": {
        "label": "설비 기인",
        "vision_pattern_group": "edge",
        "sensor_condition": "random",
        "vibration_condition": "random",
        "expected_dept": "M-ENG",
    },
    "SC-NG": {
        "label": "정상",
        "vision_pattern_group": "none",
        "sensor_condition": "random",
        "vibration_condition": "random",
        "expected_dept": None,
    },
}


def build_fake_ctx() -> SamplingContext:
    rng = np.random.RandomState(0)
    n = 30
    feature_cols = [str(i) for i in range(5)]
    data = rng.normal(0, 1, size=(n, len(feature_cols)))
    secom_df = pd.DataFrame(data, columns=feature_cols)
    secom_df["Pass/Fail"] = [-1] * (n - 5) + [1] * 5
    secom_df["Time"] = pd.date_range("2020-01-01", periods=n, freq="h")

    sensor_model = fit_sensor_model(secom_df, feature_cols, method="topn_zscore", top_n=3)
    anomaly_scores = compute_anomaly_scores_batch(sensor_model, secom_df)

    vibration_load_result = {
        "mode": "single_file",
        "files": ["f1"],
        "rms_values": [0.1],
        "stats_values": [{"rms": 0.1, "kurtosis": 3.0, "crest_factor": 4.0, "peak_to_peak": 0.5}],
    }

    wm811k_df = pd.DataFrame(
        {
            "waferMap": [np.ones((3, 3), dtype=int) for _ in range(4)],
            "lotName": ["lot1", "lot2", "lot3", "lot4"],
            "waferIndex": [1, 2, 3, 4],
            "failureType": ["Edge-Ring", "Center", "Scratch", "none"],
            "pattern_group": ["edge", "center", "other", "none"],
        }
    )

    return SamplingContext(
        scenarios=FAKE_SCENARIOS,
        secom_df=secom_df,
        feature_cols=feature_cols,
        sensor_model=sensor_model,
        anomaly_scores=anomaly_scores,
        vibration_load_result=vibration_load_result,
        wm811k_df=wm811k_df,
        baseline_n=144,
    )


@pytest.fixture
def fake_ctx() -> SamplingContext:
    return build_fake_ctx()


@pytest.fixture
def fake_rules() -> dict:
    return FAKE_RULES
