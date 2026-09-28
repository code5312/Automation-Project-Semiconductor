from src.report.pdf import generate_handover_pdf


def _sample_event(event_id: str = "EVT-1") -> dict:
    return {
        "event_id": event_id,
        "scenario_id": "SC-EQ",
        "seed": 1,
        "is_simulated": True,
        "event_time": "2026-01-01T00:00:00+00:00",
        "signals": {
            "vision": {"pattern": "Edge-Ring", "pattern_group": "edge"},
            "sensor": {"anomaly_score": 0.42},
            "vibration": {"mode": "single_file", "rms": 0.12, "health_index": None, "kurtosis": 4.1, "crest_factor": 6.0},
        },
        "diagnosis": {
            "rule_id": "R2",
            "primary_dept": "M-ENG",
            "secondary_depts": ["P-ENG"],
            "mfg_hold": True,
            "scores": {"equipment": 0.7, "process": 0.2},
            "contributions": {
                "equipment": {"edge_pattern": 0.4, "vibration_abnormal": 0.2, "sensor_normal": 0.1},
                "process": {"center_pattern": 0.0, "sensor_anomaly": 0.15, "vibration_normal": 0.05},
            },
            "notes": ["health_index unavailable; using kurtosis/crest_factor-based abnormality in its place"],
        },
    }


def test_generate_handover_pdf_creates_a_valid_pdf_file(tmp_path):
    out_path = tmp_path / "report.pdf"
    result = generate_handover_pdf(_sample_event(), handovers=[], out_path=out_path)

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    with open(out_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_generate_handover_pdf_with_handover_history(tmp_path):
    out_path = tmp_path / "report_with_history.pdf"
    handovers = [
        {"from_dept": "YI", "to_dept": "M-ENG", "reason": "초기 배정", "created_at": "2026-01-01T00:01:00+00:00"},
        {"from_dept": "M-ENG", "to_dept": "P-ENG", "reason": "설비 이상 없음", "created_at": "2026-01-01T00:02:00+00:00"},
    ]
    result = generate_handover_pdf(_sample_event(), handovers=handovers, out_path=out_path)

    assert result.exists()
    assert result.stat().st_size > 0


def test_generate_handover_pdf_handles_none_primary_dept(tmp_path):
    event = _sample_event()
    event["diagnosis"]["primary_dept"] = None
    event["diagnosis"]["secondary_depts"] = []
    event["diagnosis"]["rule_id"] = "R0"

    out_path = tmp_path / "report_r0.pdf"
    result = generate_handover_pdf(event, handovers=[], out_path=out_path)

    assert result.exists()
    assert result.stat().st_size > 0


def test_generate_handover_pdf_creates_parent_directories(tmp_path):
    out_path = tmp_path / "nested" / "dir" / "report.pdf"
    result = generate_handover_pdf(_sample_event(), handovers=[], out_path=out_path)
    assert result.exists()
