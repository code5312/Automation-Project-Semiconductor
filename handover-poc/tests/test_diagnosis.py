from src.diagnosis.engine import diagnose

RULES = {
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


def test_r0_normal_closeout_when_vibration_totally_unknown():
    vision = {"pattern": "none", "pattern_group": "none"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.1, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R0"
    assert result["primary_dept"] is None
    assert result["mfg_hold"] is False


def test_r0_normal_closeout_when_single_file_vibration_is_calm():
    vision = {"pattern": "none", "pattern_group": "none"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {
        "mode": "single_file",
        "rms": 0.1,
        "health_index": None,
        "kurtosis": 3.0,
        "crest_factor": 4.0,
    }
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R0"
    assert result["primary_dept"] is None


def test_r0_blocked_when_single_file_vibration_is_impulsive():
    vision = {"pattern": "none", "pattern_group": "none"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {
        "mode": "single_file",
        "rms": 0.1,
        "health_index": None,
        "kurtosis": 6.0,
        "crest_factor": 8.0,
    }
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] != "R0"


def test_r1_mfg_hold_flag_set_when_wafer_defect_present():
    vision = {"pattern": "Edge-Ring", "pattern_group": "edge"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {"mode": "full_baseline", "rms": 0.5, "health_index": 5.0}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["mfg_hold"] is True


def test_r2_equipment_hypothesis_wins_clearly_via_health_index():
    vision = {"pattern": "Edge-Ring", "pattern_group": "edge"}
    sensor = {"anomaly_score": 0.05, "top_sensors": []}
    vibration = {"mode": "full_baseline", "rms": 0.5, "health_index": 6.0}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R2"
    assert result["primary_dept"] == "M-ENG"
    assert "P-ENG" in result["secondary_depts"]


def test_r2_equipment_hypothesis_wins_via_kurtosis_crest_fallback():
    vision = {"pattern": "Edge-Ring", "pattern_group": "edge"}
    sensor = {"anomaly_score": 0.05, "top_sensors": []}
    vibration = {
        "mode": "single_file",
        "rms": 0.5,
        "health_index": None,
        "kurtosis": 6.0,
        "crest_factor": 8.0,
    }
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R2"
    assert result["primary_dept"] == "M-ENG"
    assert result["contributions"]["equipment"]["vibration_abnormal"] == RULES["weights"]["equipment"]["vibration_abnormal"]


def test_r3_unclear_when_no_hypothesis_clears_threshold():
    vision = {"pattern": "Scratch", "pattern_group": "other"}
    sensor = {"anomaly_score": 0.5, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.2, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R3"
    assert result["primary_dept"] == "YI"


def test_health_index_none_and_no_kurtosis_is_excluded_not_treated_as_zero_or_normal():
    vision = {"pattern": "Center", "pattern_group": "center"}
    sensor = {"anomaly_score": 0.9, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.2, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)  # must not raise
    assert result["contributions"]["equipment"]["vibration_abnormal"] == 0.0
    assert result["contributions"]["process"]["vibration_normal"] == 0.0
    assert any("health_index is None" in note for note in result["notes"])


def test_kurtosis_crest_fallback_used_and_noted_when_health_index_missing():
    vision = {"pattern": "Center", "pattern_group": "center"}
    sensor = {"anomaly_score": 0.5, "top_sensors": []}
    vibration = {
        "mode": "single_file",
        "rms": 0.2,
        "health_index": None,
        "kurtosis": 4.5,  # midway between baseline (3.0) and cap (6.0) -> 0.5
        "crest_factor": 6.0,  # midway between baseline (4.0) and cap (8.0) -> 0.5
    }
    result = diagnose(vision, sensor, vibration, RULES)  # must not raise
    assert result["contributions"]["equipment"]["vibration_abnormal"] == 0.4 * 0.5
    assert result["contributions"]["process"]["vibration_normal"] == 0.2 * 0.5
    assert any("kurtosis/crest_factor" in note for note in result["notes"])
