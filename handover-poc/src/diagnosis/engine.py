"""Rule-based diagnosis engine.

Weights and thresholds live in config/rules.yaml; this module only computes
scores from them and applies the rule list. These are diagnostic scores
backed by explicit contributions -- never call them "confidence", they are
not probabilities.
"""
from typing import Optional


def _normalize_hi(health_index: Optional[float], hi_cap: float) -> Optional[float]:
    if health_index is None:
        return None
    return max(0.0, min(1.0, health_index / hi_cap))


def _normalize_hi_normal(health_index: Optional[float], hi_cap: float) -> Optional[float]:
    if health_index is None:
        return None
    return max(0.0, 1.0 - min(1.0, abs(health_index) / hi_cap))


def compute_scores(vision: dict, sensor: dict, vibration: dict, rules: dict) -> tuple[dict, dict, list[str]]:
    """Returns (scores, contributions, notes)."""
    weights = rules["weights"]
    hi_cap = rules["thresholds"]["hi_cap"]
    notes: list[str] = []

    health_index = vibration.get("health_index")
    anomaly_score = sensor["anomaly_score"]
    pattern_group = vision["pattern_group"]

    hi_norm = _normalize_hi(health_index, hi_cap)
    hi_normal_norm = _normalize_hi_normal(health_index, hi_cap)
    if health_index is None:
        notes.append(
            "vibration.health_index is None (no baseline available) -- "
            "vibration contribution set to 0 for both hypotheses, not faked as 'normal'"
        )

    eq_w = weights["equipment"]
    equipment_contrib = {
        "edge_pattern": eq_w["edge_pattern"] * (1.0 if pattern_group == "edge" else 0.0),
        "vibration_hi": eq_w["vibration_hi"] * (hi_norm if hi_norm is not None else 0.0),
        "sensor_normal": eq_w["sensor_normal"] * (1.0 - anomaly_score),
    }

    pr_w = weights["process"]
    process_contrib = {
        "center_pattern": pr_w["center_pattern"] * (1.0 if pattern_group == "center" else 0.0),
        "sensor_anomaly": pr_w["sensor_anomaly"] * anomaly_score,
        "vibration_normal": pr_w["vibration_normal"] * (hi_normal_norm if hi_normal_norm is not None else 0.0),
    }

    scores = {
        "equipment": sum(equipment_contrib.values()),
        "process": sum(process_contrib.values()),
    }
    contributions = {"equipment": equipment_contrib, "process": process_contrib}
    return scores, contributions, notes


def diagnose(vision: dict, sensor: dict, vibration: dict, rules: dict) -> dict:
    """Apply R0-R3 and return a dict matching the Diagnosis schema."""
    depts = rules["depts"]
    thresholds = rules["thresholds"]

    scores, contributions, notes = compute_scores(vision, sensor, vibration, rules)

    pattern_group = vision["pattern_group"]
    anomaly_score = sensor["anomaly_score"]
    health_index = vibration.get("health_index")

    # R1: a wafer-map defect always triggers an MFG hold, regardless of which
    # rule below ends up deciding the primary department.
    mfg_hold = pattern_group != "none"

    vibration_normal_or_unknown = health_index is None or abs(health_index) <= thresholds["hi_normal_max"]

    if pattern_group == "none" and anomaly_score < thresholds["sensor_low"] and vibration_normal_or_unknown:
        return {
            "rule_id": "R0",
            "scores": scores,
            "contributions": contributions,
            "primary_dept": None,
            "secondary_depts": [],
            "mfg_hold": mfg_hold,
            "notes": notes + [
                "R0: no vision defect, low sensor anomaly, vibration normal/unknown -> normal close-out"
            ],
        }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_hyp, top_score = ranked[0]
    second_score = ranked[1][1]

    if top_score >= thresholds["score_min"] and (top_score - second_score) >= thresholds["score_gap_min"]:
        return {
            "rule_id": "R2",
            "scores": scores,
            "contributions": contributions,
            "primary_dept": depts[top_hyp],
            "secondary_depts": [depts[h] for h, _ in ranked[1:]],
            "mfg_hold": mfg_hold,
            "notes": notes + [
                f"R2: top hypothesis '{top_hyp}' score={top_score:.3f} clears score_min/score_gap_min"
            ],
        }

    return {
        "rule_id": "R3",
        "scores": scores,
        "contributions": contributions,
        "primary_dept": depts["unclear"],
        "secondary_depts": [depts[h] for h, _ in ranked],
        "mfg_hold": mfg_hold,
        "notes": notes + [
            "R3: no hypothesis clears score_min/score_gap_min -> YI must assign primary department"
        ],
    }
