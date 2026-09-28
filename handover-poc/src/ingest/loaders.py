"""Loaders for raw datasets (UCI SECOM, NASA IMS bearing vibration).

Both loaders raise on any load failure. They never substitute a silent
default value for missing or malformed data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# UCI SECOM documentation: Pass/Fail encodes -1 = pass (normal), 1 = fail
# (defect). Verified directly against uci-secom.csv (104 fails / 1567 rows).
SECOM_LABEL_PASS = -1
SECOM_LABEL_FAIL = 1


def load_secom(path: str | Path) -> pd.DataFrame:
    """Load SECOM csv, drop constant columns, impute using normal-row medians.

    Returns a DataFrame with columns: Time (datetime), Pass/Fail (int),
    and the remaining sensor columns (constant columns removed).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SECOM file not found: {path}")

    df = pd.read_csv(path)
    if "Time" not in df.columns or "Pass/Fail" not in df.columns:
        raise ValueError("SECOM csv is missing required 'Time' or 'Pass/Fail' columns")

    df["Time"] = pd.to_datetime(df["Time"], format="%Y-%m-%d %H:%M:%S", errors="raise")

    label_values = set(df["Pass/Fail"].unique().tolist())
    if not label_values <= {SECOM_LABEL_PASS, SECOM_LABEL_FAIL}:
        raise ValueError(f"Unexpected Pass/Fail values in SECOM data: {label_values}")

    feature_cols = [c for c in df.columns if c not in ("Time", "Pass/Fail")]
    constant_cols = [c for c in feature_cols if df[c].nunique(dropna=True) <= 1]
    df = df.drop(columns=constant_cols)
    feature_cols = [c for c in feature_cols if c not in constant_cols]

    normal_mask = df["Pass/Fail"] == SECOM_LABEL_PASS
    medians = df.loc[normal_mask, feature_cols].median()
    df[feature_cols] = df[feature_cols].fillna(medians)

    if df[feature_cols].isna().any().any():
        raise ValueError("SECOM data still contains NaNs after median imputation")

    return df.reset_index(drop=True)


def _channel_stats(col: np.ndarray) -> dict:
    """Time-domain stats for one vibration channel, computable from a single
    file (no cross-file baseline needed). kurtosis here is the raw (Pearson)
    kurtosis, ~3.0 for Gaussian noise; crest_factor is peak/RMS. Both rise
    for impulsive signals, which is the standard baseline-free indicator of
    a developing bearing fault in the vibration-analysis literature.
    """
    rms = float(np.sqrt(np.mean(np.square(col))))
    mean = float(np.mean(col))
    std = float(np.std(col))
    peak = float(np.max(np.abs(col)))
    centered = col - mean
    m2 = float(np.mean(centered**2))
    m4 = float(np.mean(centered**4))
    kurtosis = m4 / (m2**2) if m2 > 0 else float("nan")
    crest_factor = peak / rms if rms > 0 else float("nan")
    return {
        "rms": rms,
        "std": std,
        "peak": peak,
        "peak_to_peak": float(np.max(col) - np.min(col)),
        "crest_factor": crest_factor,
        "kurtosis": kurtosis,
    }


def _load_one_vibration_file(path: Path, channel: int) -> dict:
    data = np.loadtxt(path)
    if data.ndim != 2 or data.shape[1] < channel:
        raise ValueError(f"Unexpected vibration file shape {data.shape} in {path}")
    return _channel_stats(data[:, channel - 1])


def load_vibration_rms(path: str | Path, channel: int = 1) -> dict:
    """Compute RMS and other time-domain stats of one channel for one or
    many NASA IMS bearing files.

    `path` may be a single file or a directory of files (sorted by filename,
    which is also the timestamp, to preserve order). Either way: if exactly
    one file is found, the result is mode="single_file" (no baseline
    possible); if more than one, mode="full_baseline".

    Raises if the path does not exist, contains no files, or a file cannot
    be parsed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Vibration path not found: {path}")

    if path.is_file():
        files = [path]
    else:
        files = sorted(p for p in path.iterdir() if p.is_file())
        if not files:
            raise ValueError(f"No vibration files found in directory: {path}")

    stats_values = [_load_one_vibration_file(f, channel) for f in files]
    rms_values = [s["rms"] for s in stats_values]

    mode = "single_file" if len(files) == 1 else "full_baseline"
    return {
        "mode": mode,
        "files": [f.name for f in files],
        "rms_values": rms_values,
        "stats_values": stats_values,
    }
