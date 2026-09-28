import pytest

from src.handover.tracker import validate_handover
from src.storage import repository


# --- validate_handover (pure) ---

def test_validate_handover_accepts_known_transition():
    validate_handover("YI", "M-ENG", "wafer defect confirmed edge pattern")


def test_validate_handover_rejects_unknown_dept():
    with pytest.raises(ValueError):
        validate_handover("YI", "QA", "typo department")


def test_validate_handover_rejects_empty_reason():
    with pytest.raises(ValueError):
        validate_handover("YI", "M-ENG", "   ")


def test_validate_handover_rejects_noop_reassignment():
    with pytest.raises(ValueError):
        validate_handover("M-ENG", "M-ENG", "still investigating")


def test_validate_handover_accepts_reopen_from_none():
    validate_handover(None, "YI", "reopened after customer complaint")


# --- repository handover persistence ---

def _sample_event(event_id: str, primary_dept: str = "YI") -> dict:
    return {
        "event_id": event_id,
        "scenario_id": "SC-UN",
        "seed": 1,
        "is_simulated": True,
        "event_time": "2026-01-01T00:00:00+00:00",
        "signals": {
            "vision": {"pattern_group": "other", "pattern": "Scratch"},
            "sensor": {"anomaly_score": 0.5},
            "vibration": {"mode": "single_file"},
        },
        "diagnosis": {
            "rule_id": "R3",
            "primary_dept": primary_dept,
            "mfg_hold": False,
            "scores": {"equipment": 0.3, "process": 0.3},
        },
    }


def test_add_handover_requires_existing_event(tmp_path):
    db_path = tmp_path / "handover.db"
    with pytest.raises(ValueError):
        repository.add_handover(db_path, "EVT-does-not-exist", "M-ENG", "assigning root-cause owner")


def test_first_handover_uses_event_primary_dept_as_from(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="YI"))

    record = repository.add_handover(db_path, "EVT-1", "M-ENG", "assigning root-cause owner")

    assert record["from_dept"] == "YI"
    assert record["to_dept"] == "M-ENG"


def test_handovers_chain_from_previous_to_dept(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="YI"))

    repository.add_handover(db_path, "EVT-1", "M-ENG", "initial assignment")
    second = repository.add_handover(db_path, "EVT-1", "P-ENG", "M-ENG found no equipment fault")

    assert second["from_dept"] == "M-ENG"
    assert second["to_dept"] == "P-ENG"
    assert repository.get_current_dept(db_path, "EVT-1") == "P-ENG"


def test_list_handovers_is_ordered_oldest_first(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="YI"))
    repository.add_handover(db_path, "EVT-1", "M-ENG", "step 1")
    repository.add_handover(db_path, "EVT-1", "P-ENG", "step 2")
    repository.add_handover(db_path, "EVT-1", "YI", "step 3")

    history = repository.list_handovers(db_path, "EVT-1")
    assert [h["to_dept"] for h in history] == ["M-ENG", "P-ENG", "YI"]


def test_pingpong_count_reflects_number_of_handovers(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="YI"))
    assert repository.get_pingpong_count(db_path, "EVT-1") == 0

    repository.add_handover(db_path, "EVT-1", "M-ENG", "step 1")
    repository.add_handover(db_path, "EVT-1", "P-ENG", "step 2")
    assert repository.get_pingpong_count(db_path, "EVT-1") == 2


def test_get_current_dept_falls_back_to_primary_dept_when_no_handovers(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="P-ENG"))
    assert repository.get_current_dept(db_path, "EVT-1") == "P-ENG"


def test_invalid_handover_is_rejected_and_not_persisted(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="YI"))

    with pytest.raises(ValueError):
        repository.add_handover(db_path, "EVT-1", "YI", "reassigning to the same department")

    assert repository.get_pingpong_count(db_path, "EVT-1") == 0
