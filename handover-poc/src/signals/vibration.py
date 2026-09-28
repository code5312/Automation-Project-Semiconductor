"""Vibration signal extraction from NASA IMS bearing data.

In "full_baseline" mode (many ordered files), a baseline mean/std is
computed from the first `baseline_n` files and used to normalize into a
health_index z-score. In "single_file" mode there is no baseline, so
health_index stays None -- callers (the diagnosis engine) must treat that
as "no information available", never silently as 0.

Every file also carries kurtosis/crest_factor/peak_to_peak (see
ingest/loaders.py's _channel_stats), which the diagnosis engine uses as a
baseline-free fallback abnormality signal when health_index is None --
that fallback is what makes single_file mode's vibration signal
substantive rather than a permanent "no information" placeholder.
"""
import numpy as np


def compute_baseline(rms_values: list[float], baseline_n: int = 144) -> tuple[float, float]:
    if len(rms_values) < baseline_n:
        raise ValueError(
            f"Not enough files ({len(rms_values)}) to compute a baseline of size {baseline_n}"
        )
    baseline = np.array(rms_values[:baseline_n])
    return float(baseline.mean()), float(baseline.std(ddof=0))


def extract_vibration_signal(load_result: dict, file_index: int = -1, baseline_n: int = 144) -> dict:
    """Build a vibration signal dict from an ingest.loaders.load_vibration_rms() result.

    `file_index` selects which file's RMS to report in full_baseline mode
    (default: the most recent file). Ignored in single_file mode.
    """
    mode = load_result["mode"]
    files = load_result["files"]
    rms_values = load_result["rms_values"]
    stats_values = load_result.get("stats_values")

    if mode == "single_file":
        stats = stats_values[0] if stats_values else {}
        return {
            "mode": "single_file",
            "file": files[0],
            "order": 0,
            "rms": rms_values[0],
            "health_index": None,
            "kurtosis": stats.get("kurtosis"),
            "crest_factor": stats.get("crest_factor"),
            "peak_to_peak": stats.get("peak_to_peak"),
        }

    if mode == "full_baseline":
        mu, sigma = compute_baseline(rms_values, baseline_n)
        idx = file_index if file_index >= 0 else len(files) + file_index
        rms = rms_values[idx]
        health_index = (rms - mu) / sigma if sigma > 0 else None
        stats = stats_values[idx] if stats_values else {}
        return {
            "mode": "full_baseline",
            "file": files[idx],
            "order": idx,
            "rms": rms,
            "health_index": health_index,
            "kurtosis": stats.get("kurtosis"),
            "crest_factor": stats.get("crest_factor"),
            "peak_to_peak": stats.get("peak_to_peak"),
        }

    raise ValueError(f"Unknown vibration mode: {mode}")
