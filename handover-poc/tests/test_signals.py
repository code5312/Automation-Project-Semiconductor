import numpy as np
import pandas as pd
import pytest

from src.ingest.wafer_mock import PATTERN_GROUPS, generate_wafer_map
from src.ingest.wm811k import _normalize_label, sample_wafer_record
from src.signals import sensor as sensor_mod
from src.signals import vibration as vibration_mod
from src.signals.vision import extract_vision_signal


# --- vision / wafer_mock ---

@pytest.mark.parametrize("group", list(PATTERN_GROUPS.keys()))
def test_generate_wafer_map_each_group(group):
    record = generate_wafer_map(group, seed=7)
    assert record["pattern_group"] == group
    assert record["failureType"] in PATTERN_GROUPS[group]
    signal = extract_vision_signal(record)
    assert signal["pattern_group"] == group
    assert signal["pattern"] == record["failureType"]


def test_generate_wafer_map_is_deterministic():
    a = generate_wafer_map("edge", seed=123)
    b = generate_wafer_map("edge", seed=123)
    assert a == b


# --- wm811k (label normalization + sampling, no LSWMD.pkl needed) ---

def test_normalize_label_handles_1x1_array():
    assert _normalize_label(np.array([["Edge-Ring"]])) == "Edge-Ring"


def test_normalize_label_handles_empty_array():
    assert _normalize_label(np.empty((0, 0))) is None


def _toy_wm811k_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "waferMap": [np.ones((3, 3), dtype=int), np.ones((4, 4), dtype=int)],
            "lotName": ["lot1", "lot2"],
            "waferIndex": [1, 2],
            "failureType": ["Edge-Ring", "Center"],
            "pattern_group": ["edge", "center"],
        }
    )


def test_sample_wafer_record_picks_matching_pattern_group():
    df = _toy_wm811k_df()
    record = sample_wafer_record(df, "edge", seed=1)
    assert record["pattern_group"] == "edge"
    assert record["failureType"] == "Edge-Ring"
    assert record["lotName"] == "lot1"


def test_sample_wafer_record_deterministic_for_same_seed():
    df = _toy_wm811k_df()
    a = sample_wafer_record(df, "center", seed=7)
    b = sample_wafer_record(df, "center", seed=7)
    assert a == b


def test_sample_wafer_record_raises_when_group_absent():
    df = _toy_wm811k_df()
    with pytest.raises(ValueError):
        sample_wafer_record(df, "other", seed=1)


# --- sensor ---

def _toy_secom_df(n_normal: int = 60, n_fail: int = 10, n_features: int = 8, seed: int = 0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    normal = rng.normal(0, 1, size=(n_normal, n_features))
    fail = rng.normal(4, 1, size=(n_fail, n_features))  # shifted -> should score as anomalous
    data = np.vstack([normal, fail])
    df = pd.DataFrame(data, columns=[str(i) for i in range(n_features)])
    df["Pass/Fail"] = [-1] * n_normal + [1] * n_fail
    return df


def test_sensor_normal_row_has_low_anomaly_score():
    df = _toy_secom_df()
    feature_cols = [c for c in df.columns if c != "Pass/Fail"]
    model = sensor_mod.fit_sensor_model(df, feature_cols, method="topn_zscore")
    signal = sensor_mod.extract_sensor_signal(model, df, row_idx=0)
    assert signal["anomaly_score"] < 0.5
    assert len(signal["top_sensors"]) == model.top_n
    for s in signal["top_sensors"]:
        assert s["unit"] == "unknown"
        assert s["meaning"] == "unknown"


def test_sensor_fail_row_has_higher_anomaly_score_than_normal_row():
    df = _toy_secom_df()
    feature_cols = [c for c in df.columns if c != "Pass/Fail"]
    model = sensor_mod.fit_sensor_model(df, feature_cols, method="topn_zscore")
    normal_signal = sensor_mod.extract_sensor_signal(model, df, row_idx=0)
    fail_row = int(df.index[df["Pass/Fail"] == 1][0])
    fail_signal = sensor_mod.extract_sensor_signal(model, df, row_idx=fail_row)
    assert fail_signal["anomaly_score"] > normal_signal["anomaly_score"]


# --- vibration ---

def test_vibration_single_file_mode_has_no_health_index():
    load_result = {"mode": "single_file", "files": ["f1"], "rms_values": [0.2]}
    signal = vibration_mod.extract_vibration_signal(load_result)
    assert signal["mode"] == "single_file"
    assert signal["health_index"] is None


def test_vibration_full_baseline_mode_computes_health_index():
    baseline = [0.1] * 144
    rms_values = baseline + [0.5]  # clearly elevated vs. baseline
    load_result = {
        "mode": "full_baseline",
        "files": [f"f{i}" for i in range(len(rms_values))],
        "rms_values": rms_values,
    }
    signal = vibration_mod.extract_vibration_signal(load_result, file_index=-1, baseline_n=144)
    assert signal["mode"] == "full_baseline"
    assert signal["health_index"] is not None
    assert signal["health_index"] > 0
