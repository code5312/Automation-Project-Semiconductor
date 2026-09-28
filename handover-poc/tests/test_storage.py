import json

from src.storage import repository
from src.storage.migrate import migrate_json_dir


def _sample_event(event_id: str, scenario_id: str = "SC-EQ", primary_dept: str = "M-ENG") -> dict:
    return {
        "event_id": event_id,
        "scenario_id": scenario_id,
        "seed": 1,
        "is_simulated": True,
        "event_time": "2026-01-01T00:00:00+00:00",
        "signals": {
            "vision": {"pattern_group": "edge", "pattern": "Edge-Ring"},
            "sensor": {"anomaly_score": 0.42},
            "vibration": {"mode": "single_file"},
        },
        "diagnosis": {
            "rule_id": "R2",
            "primary_dept": primary_dept,
            "mfg_hold": True,
            "scores": {"equipment": 0.7, "process": 0.2},
        },
    }


def test_init_db_creates_table(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.init_db(db_path)
    assert repository.count_events(db_path) == 0


def test_save_and_get_event_roundtrip(tmp_path):
    db_path = tmp_path / "handover.db"
    event = _sample_event("EVT-1")
    repository.save_event(db_path, event)

    fetched = repository.get_event(db_path, "EVT-1")
    assert fetched == event


def test_get_event_returns_none_when_missing(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.init_db(db_path)
    assert repository.get_event(db_path, "EVT-does-not-exist") is None


def test_save_event_upserts_by_event_id(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="M-ENG"))
    repository.save_event(db_path, _sample_event("EVT-1", primary_dept="P-ENG"))

    assert repository.count_events(db_path) == 1
    assert repository.get_event(db_path, "EVT-1")["diagnosis"]["primary_dept"] == "P-ENG"


def test_list_events_filters_by_scenario_and_dept(tmp_path):
    db_path = tmp_path / "handover.db"
    repository.save_event(db_path, _sample_event("EVT-1", scenario_id="SC-EQ", primary_dept="M-ENG"))
    repository.save_event(db_path, _sample_event("EVT-2", scenario_id="SC-PR", primary_dept="P-ENG"))
    repository.save_event(db_path, _sample_event("EVT-3", scenario_id="SC-EQ", primary_dept="P-ENG"))

    by_scenario = repository.list_events(db_path, scenario_id="SC-EQ")
    assert {e["event_id"] for e in by_scenario} == {"EVT-1", "EVT-3"}

    by_dept = repository.list_events(db_path, primary_dept="P-ENG")
    assert {e["event_id"] for e in by_dept} == {"EVT-2", "EVT-3"}

    by_both = repository.list_events(db_path, scenario_id="SC-EQ", primary_dept="P-ENG")
    assert {e["event_id"] for e in by_both} == {"EVT-3"}


def test_list_events_respects_limit(tmp_path):
    db_path = tmp_path / "handover.db"
    for i in range(5):
        repository.save_event(db_path, _sample_event(f"EVT-{i}"))
    assert len(repository.list_events(db_path, limit=2)) == 2


def test_migrate_json_dir_persists_all_files(tmp_path):
    json_dir = tmp_path / "events"
    json_dir.mkdir()
    for i in range(3):
        event = _sample_event(f"EVT-{i}")
        with open(json_dir / f"EVT-{i}.json", "w", encoding="utf-8") as f:
            json.dump(event, f)

    db_path = tmp_path / "handover.db"
    count = migrate_json_dir(json_dir, db_path)

    assert count == 3
    assert repository.count_events(db_path) == 3
