"""Deterministic mock generator for WM-811K-style wafer maps.

The production path now uses real WM-811K data (see ingest/wm811k.py,
which imports PATTERN_GROUPS from this module to stay consistent). This
module is kept as a fast, dependency-free fixture for tests and offline
dev work that don't want to load the 2GB LSWMD.pkl.
"""
import numpy as np

WAFER_SIZE = 26

# WM-811K's 8 labeled failure types (+ "none"), grouped the way this PoC's
# scenarios need them.
PATTERN_GROUPS: dict[str, list[str]] = {
    "edge": ["Edge-Ring", "Edge-Loc"],
    "center": ["Center", "Donut", "Loc"],
    "other": ["Scratch", "Random", "Near-full"],
    "none": ["none"],
}


def _circle_mask(size: int) -> np.ndarray:
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    r = size / 2
    return (yy - c) ** 2 + (xx - c) ** 2 <= r ** 2


def _apply_pattern(mask: np.ndarray, failure_type: str, rng: np.random.RandomState) -> np.ndarray:
    size = mask.shape[0]
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    dist = np.sqrt((yy - c) ** 2 + (xx - c) ** 2)
    max_r = size / 2

    wafer = np.where(mask, 1, 0).astype(int)

    def defect(prob_map: np.ndarray, base_rate: float) -> None:
        die_idx = np.argwhere(mask)
        for y, x in die_idx:
            if rng.random() < base_rate * prob_map[y, x]:
                wafer[y, x] = 2

    if failure_type == "Edge-Ring":
        ring = np.clip((dist / max_r - 0.75) / 0.25, 0, 1)
        defect(ring, 0.9)
    elif failure_type == "Edge-Loc":
        angle = rng.uniform(0, 2 * np.pi)
        spread = rng.uniform(0.4, 0.8)
        ang = np.arctan2(yy - c, xx - c)
        angular = np.exp(-((ang - angle) ** 2) / (2 * spread ** 2))
        edge = np.clip((dist / max_r - 0.6) / 0.4, 0, 1)
        defect(angular * edge, 0.9)
    elif failure_type == "Center":
        center_p = np.clip(1 - dist / (max_r * 0.35), 0, 1)
        defect(center_p, 0.85)
    elif failure_type == "Donut":
        donut = np.exp(-((dist / max_r - 0.5) ** 2) / (2 * 0.12 ** 2))
        defect(donut, 0.85)
    elif failure_type == "Loc":
        cy = rng.uniform(0.3, 0.7) * size
        cx = rng.uniform(0.3, 0.7) * size
        local = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        blob = np.clip(1 - local / (size * 0.15), 0, 1)
        defect(blob, 0.85)
    elif failure_type == "Scratch":
        angle = rng.uniform(0, np.pi)
        offset = (xx - c) * np.cos(angle) + (yy - c) * np.sin(angle)
        perp = -(xx - c) * np.sin(angle) + (yy - c) * np.cos(angle)
        line = np.exp(-(perp ** 2) / 2.0) * (np.abs(offset) < max_r * 0.9)
        defect(line, 0.7)
    elif failure_type == "Random":
        defect(np.ones_like(dist), 0.05)
    elif failure_type == "Near-full":
        defect(np.ones_like(dist), 0.85)
    elif failure_type == "none":
        pass
    else:
        raise ValueError(f"Unknown failure_type: {failure_type}")

    wafer[~mask] = 0
    return wafer


def generate_wafer_map(pattern_group: str, seed: int) -> dict:
    """Deterministically generate a mock WM-811K-style wafer map record.

    Same (pattern_group, seed) always yields the same wafer map and
    failureType (die values: 0=no die, 1=normal die, 2=defective die).
    """
    if pattern_group not in PATTERN_GROUPS:
        raise ValueError(f"Unknown pattern_group: {pattern_group}")

    rng = np.random.RandomState(seed)
    choices = PATTERN_GROUPS[pattern_group]
    failure_type = choices[int(rng.randint(0, len(choices)))]

    mask = _circle_mask(WAFER_SIZE)
    wafer = _apply_pattern(mask, failure_type, rng)

    return {
        "waferMap": wafer.tolist(),
        "failureType": failure_type,
        "pattern_group": pattern_group,
        "lotName": f"MOCK-LOT{seed:04d}",
        "waferIndex": int(rng.randint(0, 25)),
    }
