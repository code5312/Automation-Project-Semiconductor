"""Rule-based diagnosis engine.

Weights and thresholds live in config/rules.yaml; this module only computes
scores from them and applies the rule list. These are diagnostic scores
backed by explicit contributions -- never call them "confidence", they are
not probabilities.

Vibration signal note: health_index (a baseline z-score) needs many ordered
files and is never available in this project's permanent single_file mode
(see signals/vibration.py). When it's missing, vibration abnormality is
instead estimated from the file's own kurtosis and crest factor -- both are
standard, baseline-free bearing-fault indicators (a healthy signal is close
to Gaussian: kurtosis ~3, crest factor ~3-4; impulsive faults push both
higher). Only if neither health_index nor kurtosis/crest_factor is
available does vibration contribute nothing, and that is noted.
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


def _kurtosis_crest_abnormality(vibration: dict, thresholds: dict) -> Optional[float]:
    """0..1 baseline-free abnormality estimate from a single file's kurtosis
    and crest factor. Higher = more impulsive / more likely a developing
    mechanical fault. None if either stat is missing."""
    kurtosis = vibration.get("kurtosis")
    crest_factor = vibration.get("crest_factor")
    if kurtosis is None or crest_factor is None:
        return None

    k_base, k_cap = thresholds["kurtosis_baseline"], thresholds["kurtosis_cap"]
    c_base, c_cap = thresholds["crest_factor_baseline"], thresholds["crest_factor_cap"]
    k_norm = max(0.0, min(1.0, (kurtosis - k_base) / (k_cap - k_base)))
    c_norm = max(0.0, min(1.0, (crest_factor - c_base) / (c_cap - c_base)))
    return (k_norm + c_norm) / 2.0


def _vibration_components(vibration: dict, thresholds: dict) -> tuple[Optional[float], Optional[float], list[str]]:
    """Returns (equipment_component, process_component, notes), each in
    [0,1], or (None, None, notes) if no vibration information is available
    at all. equipment_component is high when vibration looks abnormal
    (supports the equipment hypothesis); process_component is high when
    vibration looks calm (supports the process hypothesis, i.e. "this is
    probably not an equipment problem")."""
    health_index = vibration.get("health_index")
    if health_index is not None:
        hi_cap = thresholds["hi_cap"]
        return _normalize_hi(health_index, hi_cap), _normalize_hi_normal(health_index, hi_cap), []

    abnormality = _kurtosis_crest_abnormality(vibration, thresholds)
    if abnormality is not None:
        note = (
            f"health_index unavailable; using kurtosis/crest_factor-based "
            f"abnormality={abnormality:.3f} in its place"
        )
        return abnormality, 1.0 - abnormality, [note]

    note = (
        "vibration.health_index is None and kurtosis/crest_factor unavailable -- "
        "vibration contribution set to 0 for both hypotheses, not faked as 'normal'"
    )
    return None, None, [note]


def compute_scores(vision: dict, sensor: dict, vibration: dict, rules: dict) -> tuple[dict, dict, list[str]]:
    """Returns (scores, contributions, notes)."""
    weights = rules["weights"]
    thresholds = rules["thresholds"]

    anomaly_score = sensor["anomaly_score"]
    pattern_group = vision["pattern_group"]

    vib_equipment, vib_process, notes = _vibration_components(vibration, thresholds)

    eq_w = weights["equipment"]
    equipment_contrib = {
        "edge_pattern": eq_w["edge_pattern"] * (1.0 if pattern_group == "edge" else 0.0),
        "vibration_abnormal": eq_w["vibration_abnormal"] * (vib_equipment if vib_equipment is not None else 0.0),
        "sensor_normal": eq_w["sensor_normal"] * (1.0 - anomaly_score),
    }

    pr_w = weights["process"]
    process_contrib = {
        "center_pattern": pr_w["center_pattern"] * (1.0 if pattern_group == "center" else 0.0),
        "sensor_anomaly": pr_w["sensor_anomaly"] * anomaly_score,
        "vibration_normal": pr_w["vibration_normal"] * (vib_process if vib_process is not None else 0.0),
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

    if health_index is not None:
        vibration_calm = abs(health_index) <= thresholds["hi_normal_max"]
    else:
        abnormality = _kurtosis_crest_abnormality(vibration, thresholds)
        vibration_calm = abnormality is None or abnormality <= thresholds["abnormality_low_max"]

    if pattern_group == "none" and anomaly_score < thresholds["sensor_low"] and vibration_calm:
        return {
            "rule_id": "R0",
            "scores": scores,
            "contributions": contributions,
            "primary_dept": None,
            "secondary_depts": [],
            "mfg_hold": mfg_hold,
            "notes": notes + [
                "R0: no vision defect, low sensor anomaly, vibration calm/unknown -> normal close-out"
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
