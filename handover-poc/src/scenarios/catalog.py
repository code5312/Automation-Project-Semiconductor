"""Scenario catalog: deterministically samples SECOM rows, wafer pattern
groups, and (when available) vibration files for one event, driven by
config/scenarios.yaml.

Building a SamplingContext does real I/O (loading SECOM/vibration data,
fitting the sensor model) once; `sample()` itself is a pure function of
(scenario_id, seed, ctx).
"""
import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from src.ingest import loaders
from src.ingest.wm811k import load_wm811k, sample_wafer_record
from src.signals.sensor import SensorModel, compute_anomaly_scores_batch, extract_sensor_signal, fit_sensor_model
from src.signals.vibration import compute_baseline, extract_vibration_signal


@dataclass
class SamplingContext:
    scenarios: dict
    secom_df: pd.DataFrame
    feature_cols: list[str]
    sensor_model: SensorModel
    anomaly_scores: pd.Series
    vibration_load_result: dict
    wm811k_df: pd.DataFrame
    baseline_n: int


def load_scenarios_config(path: str | Path) -> dict:
    with open(Path(path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_sampling_context(config_path: str | Path = "config/scenarios.yaml") -> SamplingContext:
    config = load_scenarios_config(config_path)
    sampling_cfg = config["sampling"]

    secom_df = loaders.load_secom(sampling_cfg["secom_path"])
    feature_cols = [c for c in secom_df.columns if c not in ("Time", "Pass/Fail")]

    sensor_model = fit_sensor_model(
        secom_df, feature_cols, method=sampling_cfg.get("sensor_method", "topn_zscore"), top_n=5
    )
    anomaly_scores = compute_anomaly_scores_batch(sensor_model, secom_df)

    vibration_load_result = loaders.load_vibration_rms(sampling_cfg["vibration_path"])
    wm811k_df = load_wm811k(sampling_cfg["wm811k_path"])

    return SamplingContext(
        scenarios=config["scenarios"],
        secom_df=secom_df,
        feature_cols=feature_cols,
        sensor_model=sensor_model,
        anomaly_scores=anomaly_scores,
        vibration_load_result=vibration_load_result,
        wm811k_df=wm811k_df,
        baseline_n=sampling_cfg.get("baseline_n", 144),
    )


def _select_sensor_row(ctx: SamplingContext, condition: str, seed: int) -> int:
    df = ctx.secom_df
    scores = ctx.anomaly_scores
    rng = random.Random(seed)

    if condition == "anomaly_score_percentile_below_50":
        median = scores.median()
        candidates = scores[scores < median].index.tolist()
    elif condition == "fail_row_anomaly_top_20pct":
        fail_idx = df.index[df["Pass/Fail"] == 1]
        fail_scores = scores.loc[fail_idx]
        cutoff = fail_scores.quantile(0.8)
        candidates = fail_scores[fail_scores >= cutoff].index.tolist()
    elif condition == "pass_row_anomaly_below_50":
        pass_idx = df.index[df["Pass/Fail"] == -1]
        pass_scores = scores.loc[pass_idx]
        median = pass_scores.median()
        candidates = pass_scores[pass_scores < median].index.tolist()
    elif condition == "random":
        candidates = df.index.tolist()
    else:
        raise ValueError(f"Unknown sensor_condition: {condition}")

    if not candidates:
        raise ValueError(f"No SECOM rows matched sensor_condition '{condition}'")

    return int(rng.choice(candidates))


def _select_vibration_file_index(ctx: SamplingContext, condition: str, seed: int) -> int:
    """Only reachable once >1 vibration file is available (full_baseline mode)."""
    rms_values = ctx.vibration_load_result["rms_values"]
    mu, sigma = compute_baseline(rms_values, ctx.baseline_n)
    rng = random.Random(seed)
    n = len(rms_values)

    def hi(i: int) -> float:
        return (rms_values[i] - mu) / sigma if sigma > 0 else 0.0

    if condition == "health_index_ge_3":
        candidates = [i for i in range(n) if hi(i) >= 3]
    elif condition == "baseline_range":
        candidates = [i for i in range(n) if abs(hi(i)) <= 1.0]
    elif condition == "random":
        candidates = list(range(n))
    else:
        raise ValueError(f"Unknown vibration_condition: {condition}")

    if not candidates:
        raise ValueError(f"No vibration files matched vibration_condition '{condition}'")

    return rng.choice(candidates)


def sample(scenario_id: str, seed: int, ctx: SamplingContext) -> dict:
    """Deterministically sample vision/sensor/vibration source material for one event."""
    if scenario_id not in ctx.scenarios:
        raise ValueError(f"Unknown scenario_id: {scenario_id}")

    cfg = ctx.scenarios[scenario_id]
    notes: list[str] = []

    wafer_record = sample_wafer_record(ctx.wm811k_df, cfg["vision_pattern_group"], seed)

    row_idx = _select_sensor_row(ctx, cfg["sensor_condition"], seed)
    sensor_signal = extract_sensor_signal(ctx.sensor_model, ctx.secom_df, row_idx)

    if ctx.vibration_load_result["mode"] == "single_file":
        notes.append(
            f"vibration_condition '{cfg['vibration_condition']}' ignored: only a single "
            "vibration file is available, so there is no baseline to evaluate it against"
        )
        vibration_signal = extract_vibration_signal(ctx.vibration_load_result)
    else:
        file_index = _select_vibration_file_index(ctx, cfg["vibration_condition"], seed)
        vibration_signal = extract_vibration_signal(
            ctx.vibration_load_result, file_index=file_index, baseline_n=ctx.baseline_n
        )

    return {
        "wafer_record": wafer_record,
        "sensor_row": row_idx,
        "sensor_time": ctx.secom_df.loc[row_idx, "Time"].isoformat(),
        "sensor_signal": sensor_signal,
        "vibration_signal": vibration_signal,
        "notes": notes,
    }
