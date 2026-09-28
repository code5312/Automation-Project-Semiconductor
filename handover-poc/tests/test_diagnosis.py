from src.diagnosis.engine import diagnose

RULES = {
    "weights": {
        "equipment": {"edge_pattern": 0.4, "vibration_hi": 0.4, "sensor_normal": 0.2},
        "process": {"center_pattern": 0.3, "sensor_anomaly": 0.5, "vibration_normal": 0.2},
    },
    "thresholds": {
        "hi_cap": 6,
        "hi_normal_max": 1.0,
        "sensor_low": 0.3,
        "score_min": 0.6,
        "score_gap_min": 0.15,
    },
    "depts": {"equipment": "M-ENG", "process": "P-ENG", "unclear": "YI"},
}


def test_r0_normal_closeout():
    vision = {"pattern": "none", "pattern_group": "none"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.1, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R0"
    assert result["primary_dept"] is None
    assert result["mfg_hold"] is False


def test_r1_mfg_hold_flag_set_when_wafer_defect_present():
    vision = {"pattern": "Edge-Ring", "pattern_group": "edge"}
    sensor = {"anomaly_score": 0.1, "top_sensors": []}
    vibration = {"mode": "full_baseline", "rms": 0.5, "health_index": 5.0}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["mfg_hold"] is True


def test_r2_equipment_hypothesis_wins_clearly():
    vision = {"pattern": "Edge-Ring", "pattern_group": "edge"}
    sensor = {"anomaly_score": 0.05, "top_sensors": []}
    vibration = {"mode": "full_baseline", "rms": 0.5, "health_index": 6.0}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R2"
    assert result["primary_dept"] == "M-ENG"
    assert "P-ENG" in result["secondary_depts"]


def test_r3_unclear_when_no_hypothesis_clears_threshold():
    vision = {"pattern": "Scratch", "pattern_group": "other"}
    sensor = {"anomaly_score": 0.5, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.2, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)
    assert result["rule_id"] == "R3"
    assert result["primary_dept"] == "YI"


def test_health_index_none_is_excluded_not_treated_as_zero_or_normal():
    vision = {"pattern": "Center", "pattern_group": "center"}
    sensor = {"anomaly_score": 0.9, "top_sensors": []}
    vibration = {"mode": "single_file", "rms": 0.2, "health_index": None}
    result = diagnose(vision, sensor, vibration, RULES)  # must not raise
    assert result["contributions"]["equipment"]["vibration_hi"] == 0.0
    assert result["contributions"]["process"]["vibration_normal"] == 0.0
    assert any("health_index is None" in note for note in result["notes"])
