import pytest

from src.ingest import validate


def _valid_event() -> dict:
    return {
        "event_id": "EVT-20250101T000000-AB12",
        "scenario_id": "SC-EQ",
        "seed": 42,
        "is_simulated": True,
        "event_time": "2025-01-01T00:00:00+00:00",
        "signals": {
            "vision": {
                "source": "WM-811K (LSWMD.pkl)",
                "source_ref": {"lotName": "lot1", "waferIndex": 3, "row": 5},
                "source_time": None,
                "pattern": "Edge-Ring",
                "pattern_group": "edge",
            },
            "sensor": {
                "source": "UCI SECOM",
                "source_ref": {"row": 2},
                "source_time": "2008-07-19T13:17:00",
                "anomaly_score": 0.31,
                "top_sensors": [
                    {"sensor_id": "21", "z": 0.4, "unit": "unknown", "meaning": "unknown"}
                ],
            },
            "vibration": {
                "source": "NASA IMS Set 2, channel 1",
                "source_ref": {"file": "2004.02.12.10.32.39", "order": 0},
                "source_time": "2004-02-12T10:32:39",
                "mode": "single_file",
                "rms": 0.19,
                "health_index": None,
            },
        },
        "diagnosis": {
            "rule_id": "R2",
            "scores": {"equipment": 0.87, "process": 0.16},
            "contributions": {"equipment": {"edge_pattern": 0.4}},
            "primary_dept": "M-ENG",
            "secondary_depts": ["P-ENG"],
            "mfg_hold": True,
            "notes": [],
        },
    }


# --- check_join_keys ---

def test_check_join_keys_valid():
    validate.check_join_keys(_valid_event(), secom_row_count=1567, vibration_file_count=1)


def test_check_join_keys_sensor_row_out_of_range():
    event = _valid_event()
    event["signals"]["sensor"]["source_ref"]["row"] = 9999
    with pytest.raises(ValueError):
        validate.check_join_keys(event, secom_row_count=1567, vibration_file_count=1)


def test_check_join_keys_single_file_order_must_be_zero():
    event = _valid_event()
    event["signals"]["vibration"]["source_ref"]["order"] = 5
    with pytest.raises(ValueError):
        validate.check_join_keys(event, secom_row_count=1567, vibration_file_count=1)


def test_check_join_keys_vision_missing_lot_name():
    event = _valid_event()
    event["signals"]["vision"]["source_ref"]["lotName"] = ""
    with pytest.raises(ValueError):
        validate.check_join_keys(event, secom_row_count=1567, vibration_file_count=1)


def test_check_join_keys_wm811k_row_out_of_range():
    event = _valid_event()
    with pytest.raises(ValueError):
        validate.check_join_keys(
            event, secom_row_count=1567, vibration_file_count=1, wm811k_row_count=3
        )


def test_check_join_keys_wm811k_row_check_skipped_when_count_not_given():
    event = _valid_event()
    event["signals"]["vision"]["source_ref"]["row"] = 999999
    validate.check_join_keys(event, secom_row_count=1567, vibration_file_count=1)


# --- check_time_separation ---

def test_check_time_separation_valid():
    validate.check_time_separation(_valid_event())


def test_check_time_separation_vision_source_time_must_be_none():
    event = _valid_event()
    event["signals"]["vision"]["source_time"] = "2020-01-01T00:00:00"
    with pytest.raises(ValueError):
        validate.check_time_separation(event)


# --- check_unit_semantics ---

def test_check_unit_semantics_valid():
    validate.check_unit_semantics(_valid_event())


def test_check_unit_semantics_empty_unit_rejected():
    event = _valid_event()
    event["signals"]["sensor"]["top_sensors"][0]["unit"] = ""
    with pytest.raises(ValueError):
        validate.check_unit_semantics(event)


# --- check_secom_label_encoding ---

def test_check_secom_label_encoding_valid():
    validate.check_secom_label_encoding([-1, 1, -1, -1, 1])


def test_check_secom_label_encoding_rejects_bad_value():
    with pytest.raises(ValueError):
        validate.check_secom_label_encoding([-1, 1, 0])


# --- load_or_fail ---

def test_load_or_fail_returns_value():
    assert validate.load_or_fail(lambda: 42) == 42


def test_load_or_fail_propagates_exception():
    def boom():
        raise FileNotFoundError("nope")

    with pytest.raises(FileNotFoundError):
        validate.load_or_fail(boom)
