"""Loader for the real WM-811K dataset (LSWMD.pkl).

LSWMD.pkl was pickled with a pandas/numpy version old enough that:

1) its Index classes still live under the long-removed `pandas.indexes.*`
   module path (pre-0.20 layout) -- modern pandas' pickle_compat shim only
   covers back to ~1.0, so we extend its class-location map on the fly for
   the handful of classes this file actually uses.
2) it was written by Python 2, so raw numpy array bytes come through the
   pickle stream as STRING opcodes; unpickling those with the default
   ASCII text encoding raises UnicodeDecodeError. We decode with 'latin1'
   instead (numpy's own documented fix for this exact py2 pickle issue).

The full file has 811,457 rows but only 172,950 are labeled (failureType
present); loading it goes through pickle's pure-Python Unpickler (the
compat shim can't use the C one), which takes several minutes. Since disk
space here is too tight to keep a second full copy around, `load_wm811k`
caches only the small labeled subset (~170K rows, tens of MB) next to the
source file in the modern pickle format, and reuses that cache on future
calls instead of re-parsing the original 2GB file every time.
"""
import pickle
import random
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pandas.compat.pickle_compat as pc

from src.ingest.wafer_mock import PATTERN_GROUPS

EXPECTED_COLUMNS = ["waferMap", "dieSize", "lotName", "waferIndex", "trianTestLabel", "failureType"]


def _guess_index_target(module: str, name: str) -> Optional[tuple[str, str]]:
    if not module.startswith("pandas.indexes"):
        return None
    if name in ("Int64Index", "UInt64Index", "Float64Index"):
        return "pandas.core.indexes.base", "Index"
    if name == "RangeIndex":
        return "pandas.core.indexes.range", "RangeIndex"
    if name == "MultiIndex":
        return "pandas.core.indexes.multi", "MultiIndex"
    tail = module.split(".")[-1]
    return f"pandas.core.indexes.{tail}", name


def _patched_find_class(self, module, name):
    key = (module, name)
    if key in pc._class_locations_map:
        real_module, real_name = pc._class_locations_map[key]
        return pickle._Unpickler.find_class(self, real_module, real_name)
    try:
        return pickle._Unpickler.find_class(self, module, name)
    except (ModuleNotFoundError, AttributeError):
        guess = _guess_index_target(module, name)
        if guess is None:
            raise
        pc._class_locations_map[key] = guess
        return pickle._Unpickler.find_class(self, *guess)


def _load_raw_pickle(path: Path) -> pd.DataFrame:
    orig_find_class = pc.Unpickler.find_class
    pc.Unpickler.find_class = _patched_find_class
    try:
        with open(path, "rb") as f:
            return pc.Unpickler(f, encoding="latin1").load()
    finally:
        pc.Unpickler.find_class = orig_find_class


def _normalize_label(value) -> Optional[str]:
    """failureType/trianTestLabel are stored as a 1x1 object array (from the
    original .mat import), or an empty array when absent."""
    if isinstance(value, np.ndarray):
        flat = value.reshape(-1)
        return str(flat[0]) if flat.size else None
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    if value in (None, ""):
        return None
    return str(value)


def _default_cache_path(path: Path) -> Path:
    return path.with_name("wm811k_labeled_cache.pkl")


def load_wm811k(path: str | Path, cache_path: Optional[str | Path] = None) -> pd.DataFrame:
    """Load the labeled subset of WM-811K (172,950 of 811,457 rows), with
    failureType/trianTestLabel normalized to plain strings and a
    pattern_group column added.

    Raises if the source file does not exist or has an unexpected shape --
    never falls back to a placeholder.
    """
    path = Path(path)
    cache_path = Path(cache_path) if cache_path is not None else _default_cache_path(path)

    if cache_path.exists():
        return pd.read_pickle(cache_path)

    if not path.exists():
        raise FileNotFoundError(f"WM-811K file not found: {path}")

    df = _load_raw_pickle(path)
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected LSWMD.pkl columns: {list(df.columns)}")

    df["failureType"] = df["failureType"].apply(_normalize_label)
    df["trianTestLabel"] = df["trianTestLabel"].apply(_normalize_label)

    labeled = df[df["failureType"].notna()].copy()
    if labeled.empty:
        raise ValueError("No labeled rows found in LSWMD.pkl")

    group_of = {name: group for group, names in PATTERN_GROUPS.items() for name in names}
    labeled["pattern_group"] = labeled["failureType"].map(group_of)
    if labeled["pattern_group"].isna().any():
        unknown = sorted(labeled.loc[labeled["pattern_group"].isna(), "failureType"].unique())
        raise ValueError(f"Unknown failureType values not in PATTERN_GROUPS: {unknown}")

    labeled = labeled.reset_index(drop=True)
    labeled.to_pickle(cache_path)
    return labeled


def sample_wafer_record(df: pd.DataFrame, pattern_group: str, seed: int) -> dict:
    """Deterministically pick one real labeled wafer from `df` matching
    `pattern_group`. Same shape as wafer_mock.generate_wafer_map's return
    value, plus a `source_row` for join-key validation."""
    if pattern_group not in PATTERN_GROUPS:
        raise ValueError(f"Unknown pattern_group: {pattern_group}")

    candidates = df.index[df["pattern_group"] == pattern_group].tolist()
    if not candidates:
        raise ValueError(f"No WM-811K rows found for pattern_group={pattern_group}")

    row_idx = random.Random(seed).choice(candidates)
    row = df.loc[row_idx]

    return {
        "waferMap": np.asarray(row["waferMap"]).tolist(),
        "failureType": row["failureType"],
        "pattern_group": pattern_group,
        "lotName": row["lotName"],
        "waferIndex": int(row["waferIndex"]),
        "source_row": int(row_idx),
    }
