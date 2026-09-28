import sys
from pathlib import Path

# Streamlit executes each page as its own standalone script, so make sure
# the project root is importable as `src...` regardless of the launch cwd
# (sys.path[0] otherwise depends on how/where `streamlit run` was invoked).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from src.dashboard.common import get_ctx, get_db_path, get_rules, inject_theme
from src.cli import build_event
from src.handover.tracker import VALID_DEPTS
from src.storage import repository as repo

st.set_page_config(page_title="이벤트 목록", page_icon="📋", layout="wide")
inject_theme()

# Fixed dept -> emoji mapping, same order/hue family as common.DEPT_COLORS,
# so a dept reads the same color across every page even inside a plain
# st.dataframe cell (which can't render arbitrary per-cell HTML/CSS).
DEPT_EMOJI = {"YI": "🔵", "MFG": "🟠", "M-ENG": "🟢", "P-ENG": "🟡"}


def _with_dept_emoji(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        dept = r.get("current_dept")
        r["current_dept"] = f"{DEPT_EMOJI.get(dept, '⚪')} {dept}" if dept else "⚪ (없음)"
        out.append(r)
    return out


st.markdown('<p class="hp-eyebrow">EVENTS</p>', unsafe_allow_html=True)
st.title("이벤트 목록")

ctx = get_ctx()
rules = get_rules()
db_path = get_db_path()

with st.container(border=True):
    st.subheader("새 이벤트 생성")
    col1, col2, col3 = st.columns([2, 1, 1])
    scenario_id = col1.selectbox("시나리오", list(ctx.scenarios.keys()))
    seed = col2.number_input("시드", min_value=0, value=0, step=1)
    col3.write("")
    col3.write("")
    if col3.button("생성", type="primary", use_container_width=True):
        try:
            event = build_event(scenario_id, int(seed), ctx, rules)
            repo.save_event(db_path, event)
            diagnosis = event["diagnosis"]
            st.success(
                f"생성됨: {event['event_id']}  "
                f"(rule_id={diagnosis['rule_id']}, primary_dept={diagnosis['primary_dept']})"
            )
        except ValueError as e:
            st.error(str(e))

st.write("")

col1, col2, col3 = st.columns(3)
scenario_filter = col1.selectbox("시나리오 필터", ["(전체)"] + list(ctx.scenarios.keys()))
dept_filter = col2.selectbox("현재 담당 부서 필터", ["(전체)"] + list(VALID_DEPTS))
limit = col3.number_input("표시 개수", min_value=10, max_value=1000, value=100, step=10)

rows = repo.list_events_with_status(
    db_path,
    scenario_id=None if scenario_filter == "(전체)" else scenario_filter,
    current_dept=None if dept_filter == "(전체)" else dept_filter,
    limit=int(limit),
)

if not rows:
    st.info("이벤트가 없습니다. 위에서 생성해보세요.")
else:
    df = pd.DataFrame(_with_dept_emoji(rows))
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_order=[
            "event_id", "scenario_id", "current_dept", "rule_id",
            "mfg_hold", "pingpong_count", "event_time",
        ],
        column_config={
            "event_id": st.column_config.TextColumn("이벤트 ID"),
            "scenario_id": st.column_config.TextColumn("시나리오"),
            "current_dept": st.column_config.TextColumn("현재 담당"),
            "rule_id": st.column_config.TextColumn("규칙"),
            "mfg_hold": st.column_config.CheckboxColumn("MFG Hold"),
            "pingpong_count": st.column_config.NumberColumn("핑퐁", format="%d"),
            "event_time": st.column_config.DatetimeColumn("생성 시각", format="YYYY-MM-DD HH:mm"),
        },
    )
    st.caption(f"{len(rows)}건 표시 (최신순). event_id를 복사해 '이벤트 상세' 페이지에서 조회하세요.")
