import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_ctx, get_db_path, get_rules
from src.handover.tracker import VALID_DEPTS
from tests.conftest import FAKE_RULES, build_fake_ctx


def _other_dept(current: str) -> str:
    return next(d for d in VALID_DEPTS if d != current)


@pytest.fixture
def client(tmp_path):
    ctx = build_fake_ctx()
    db_path = str(tmp_path / "test.db")

    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_rules] = lambda: FAKE_RULES
    app.dependency_overrides[get_db_path] = lambda: db_path

    # Plain TestClient(app), NOT `with TestClient(app) as c`: entering it as
    # a context manager runs the app's real lifespan (which loads the real
    # SECOM/vibration/WM-811K files via build_sampling_context()) regardless
    # of the dependency_overrides above -- those only affect what's injected
    # into route handlers, not the startup hook itself.
    yield TestClient(app)

    app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_scenarios(client):
    resp = client.get("/scenarios")
    assert resp.status_code == 200
    assert "SC-EQ" in resp.json()


def test_generate_event_persists_and_is_retrievable(client):
    resp = client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    assert resp.status_code == 201
    event = resp.json()
    assert event["scenario_id"] == "SC-EQ"
    assert event["is_simulated"] is True

    fetched = client.get(f"/events/{event['event_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["event_id"] == event["event_id"]


def test_generate_event_unknown_scenario_returns_404(client):
    resp = client.post("/events/generate", json={"scenario_id": "SC-NOPE", "seed": 1})
    assert resp.status_code == 404


def test_get_event_not_found_returns_404(client):
    resp = client.get("/events/EVT-does-not-exist")
    assert resp.status_code == 404


def test_list_events_filters_by_scenario(client):
    client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    client.post("/events/generate", json={"scenario_id": "SC-NG", "seed": 2})

    resp = client.get("/events", params={"scenario_id": "SC-EQ"})
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["scenario_id"] == "SC-EQ"


def test_validate_endpoint_rejects_malformed_event(client):
    resp = client.post("/validate", json={"event": {"bad": "data"}})
    assert resp.status_code == 422


def test_validate_endpoint_accepts_generated_event(client):
    gen = client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    event = gen.json()

    resp = client.post("/validate", json={"event": event})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_handover_lifecycle(client):
    gen = client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    event = gen.json()
    event_id = event["event_id"]
    primary_dept = event["diagnosis"]["primary_dept"]
    target = _other_dept(primary_dept)

    empty = client.get(f"/events/{event_id}/handovers")
    assert empty.status_code == 200
    assert empty.json() == {
        "event_id": event_id,
        "current_dept": primary_dept,
        "pingpong_count": 0,
        "history": [],
    }

    resp = client.post(f"/events/{event_id}/handovers", json={"to_dept": target, "reason": "root-cause owner assigned"})
    assert resp.status_code == 201
    record = resp.json()
    assert record["from_dept"] == primary_dept
    assert record["to_dept"] == target

    after = client.get(f"/events/{event_id}/handovers")
    body = after.json()
    assert body["current_dept"] == target
    assert body["pingpong_count"] == 1
    assert len(body["history"]) == 1


def test_handover_unknown_event_returns_404(client):
    resp = client.post("/events/EVT-nope/handovers", json={"to_dept": "M-ENG", "reason": "x"})
    assert resp.status_code == 404


def test_handover_invalid_department_returns_422(client):
    gen = client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    event_id = gen.json()["event_id"]

    resp = client.post(f"/events/{event_id}/handovers", json={"to_dept": "QA", "reason": "typo dept"})
    assert resp.status_code == 422


def test_handover_noop_reassignment_returns_422(client):
    gen = client.post("/events/generate", json={"scenario_id": "SC-EQ", "seed": 1})
    event = gen.json()
    event_id = event["event_id"]
    primary_dept = event["diagnosis"]["primary_dept"]

    resp = client.post(f"/events/{event_id}/handovers", json={"to_dept": primary_dept, "reason": "same dept"})
    assert resp.status_code == 422


def test_get_handovers_for_unknown_event_returns_404(client):
    resp = client.get("/events/EVT-nope/handovers")
    assert resp.status_code == 404
