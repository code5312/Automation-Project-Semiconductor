"""Headless tests for the Streamlit dashboard using streamlit.testing.v1.AppTest
-- this actually executes each page script in a simulated Streamlit runtime
and captures exceptions, unlike hitting the server with plain HTTP (which
only exercises the app shell, not page scripts run over the websocket
session). src.dashboard.common's cached loaders are patched to return the
same synthetic SamplingContext/rules used by the API tests, so these don't
need the real SECOM/vibration/WM-811K files.
"""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard import common
from src.storage import repository as repo
from tests.conftest import FAKE_RULES, build_fake_ctx

# AppTest.from_file() resolves relative paths against the caller file's own
# directory (tests/), not the project root -- so build absolute paths here.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = PROJECT_ROOT / "src" / "dashboard"


def test_every_dashboard_script_has_a_correct_sys_path_bootstrap():
    """Regression test for a real bug: app.py copy-pasted pages/*.py's
    `parents[3]` bootstrap unchanged, but app.py sits one directory shallower
    (src/dashboard/app.py vs src/dashboard/pages/x.py), so it silently
    inserted the project root's *parent* instead -- `from src...` still
    worked wherever something else (pytest's own sys.path, or cwd under
    `streamlit run`) happened to paper over it, and only broke for a bare
    `python app.py`-style invocation. Check the arithmetic directly rather
    than relying on some other sys.path entry to mask a wrong depth again.
    """
    scripts = [DASHBOARD_DIR / "app.py"] + sorted((DASHBOARD_DIR / "pages").glob("*.py"))
    assert len(scripts) == 5, f"expected app.py + 4 pages, found {[s.name for s in scripts]}"

    for script in scripts:
        text = script.read_text(encoding="utf-8")
        match = re.search(r"sys\.path\.insert\(0, str\(Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]\)\)", text)
        assert match, f"{script.name} is missing the expected sys.path bootstrap line"
        depth = int(match.group(1))
        resolved = script.resolve().parents[depth]
        assert resolved == PROJECT_ROOT, (
            f"{script.name}: parents[{depth}] resolves to {resolved}, "
            f"not the project root {PROJECT_ROOT} -- from src... would fail standalone"
        )


@pytest.fixture(autouse=True)
def fake_dashboard_resources(tmp_path, monkeypatch):
    ctx = build_fake_ctx()

    common.get_ctx.clear()
    common.get_rules.clear()
    with patch("src.dashboard.common.build_sampling_context", return_value=ctx), \
         patch("src.dashboard.common.load_rules", return_value=FAKE_RULES):
        monkeypatch.setattr(common, "get_db_path", lambda: str(tmp_path / "dashboard.db"))
        yield
    common.get_ctx.clear()
    common.get_rules.clear()


def test_home_page_loads_without_exception():
    at = AppTest.from_file(str(DASHBOARD_DIR / "app.py"))
    at.run()
    assert not at.exception


def test_event_list_page_loads_and_shows_empty_state():
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "1_이벤트_목록.py"))
    at.run()
    assert not at.exception
    assert any("이벤트가 없습니다" in info.value for info in at.info)


def test_event_list_page_generate_button_creates_event():
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "1_이벤트_목록.py"))
    at.run()
    at.button[0].click().run()
    assert not at.exception
    assert any("생성됨" in s.value for s in at.success)


def test_event_detail_page_shows_error_for_unknown_event_id():
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "2_이벤트_상세.py"))
    at.run()
    at.text_input[0].set_value("EVT-does-not-exist").run()
    assert not at.exception
    assert any("찾을 수 없습니다" in e.value for e in at.error)


def _seed_event(tmp_path, event_id: str = "EVT-TEST-1", primary_dept: str = "M-ENG") -> str:
    db_path = tmp_path / "dashboard.db"
    event = {
        "event_id": event_id,
        "scenario_id": "SC-EQ",
        "seed": 1,
        "is_simulated": True,
        "event_time": "2026-01-01T00:00:00+00:00",
        "signals": {
            "vision": {"pattern_group": "edge", "pattern": "Edge-Ring"},
            "sensor": {"anomaly_score": 0.42},
            "vibration": {
                "mode": "single_file", "rms": 0.1, "health_index": None,
                "kurtosis": 4.0, "crest_factor": 6.0,
            },
        },
        "diagnosis": {
            "rule_id": "R2",
            "primary_dept": primary_dept,
            "secondary_depts": ["P-ENG"],
            "mfg_hold": True,
            "scores": {"equipment": 0.7, "process": 0.2},
            "contributions": {"equipment": {"edge_pattern": 0.4}, "process": {"sensor_anomaly": 0.2}},
            "notes": [],
        },
    }
    repo.save_event(db_path, event)
    return event_id


def test_event_detail_page_renders_valid_event_with_pdf_download_button(tmp_path):
    """This is the only test that actually reaches src/report/pdf.py's
    generate_handover_pdf() call inside the page -- the unknown-event-id
    test above stops before that point (st.stop() on a missing event)."""
    event_id = _seed_event(tmp_path)
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "2_이벤트_상세.py"))
    at.run()
    at.text_input[0].set_value(event_id).run()

    assert not at.exception
    assert len(at.download_button) == 1
    assert at.download_button[0].proto.label == "📄 PDF 다운로드"
    assert any(event_id in md.value for md in at.markdown)


def test_dept_status_page_loads_with_empty_state():
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "3_부서_현황.py"))
    at.run()
    assert not at.exception
    assert any("이벤트가 없습니다" in info.value for info in at.info)


def test_rule_tuning_page_loads_and_runs_preview():
    at = AppTest.from_file(str(DASHBOARD_DIR / "pages" / "4_규칙_튜닝.py"))
    at.run()
    assert not at.exception

    at.number_input[0].set_value(5).run()
    at.button[0].click().run()
    assert not at.exception
    assert any("전체 정확도" in m.label for m in at.metric)
