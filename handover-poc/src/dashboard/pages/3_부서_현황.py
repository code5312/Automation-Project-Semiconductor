import sys
from collections import Counter
from pathlib import Path

# Streamlit executes each page as its own standalone script, so make sure
# the project root is importable as `src...` regardless of the launch cwd
# (sys.path[0] otherwise depends on how/where `streamlit run` was invoked).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from src.dashboard.common import DEPT_COLORS, dept_badge, get_db_path, inject_theme
from src.storage import repository as repo

st.set_page_config(page_title="부서 현황", page_icon="🏢", layout="wide")
inject_theme()

st.markdown('<p class="hp-eyebrow">DEPARTMENT STATUS</p>', unsafe_allow_html=True)
st.title("부서별 처리 현황 & 핑퐁 추적")

db_path = get_db_path()
rows = repo.list_events_with_status(db_path, limit=2000)

if not rows:
    st.info("이벤트가 없습니다. '이벤트 목록' 페이지에서 먼저 생성하세요.")
    st.stop()

pingpong_rows = sorted((r for r in rows if r["pingpong_count"] > 0), key=lambda r: -r["pingpong_count"])
avg_pingpong = sum(r["pingpong_count"] for r in rows) / len(rows)

k1, k2, k3 = st.columns(3)
k1.metric("전체 이벤트", f"{len(rows):,}")
k2.metric("핑퐁 발생 이벤트", f"{len(pingpong_rows):,}", help="한 번 이상 재할당된 이벤트 수")
k3.metric("평균 핑퐁 횟수", f"{avg_pingpong:.2f}")

st.write("")
with st.container(border=True):
    st.subheader("부서별 현재 담당 건수")
    dept_counts = Counter(r["current_dept"] or "(없음)" for r in rows)
    st.bar_chart(dept_counts)
    st.markdown(
        " &nbsp;&nbsp; ".join(dept_badge(d) + f" {dept_counts.get(d, 0)}건" for d in DEPT_COLORS),
        unsafe_allow_html=True,
    )

st.write("")
with st.container(border=True):
    st.subheader("핑퐁 랭킹 (재할당이 많이 된 이벤트)")
    if pingpong_rows:
        df = pd.DataFrame(pingpong_rows[:50])
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_order=["event_id", "scenario_id", "current_dept", "pingpong_count", "rule_id"],
            column_config={
                "event_id": st.column_config.TextColumn("이벤트 ID"),
                "scenario_id": st.column_config.TextColumn("시나리오"),
                "current_dept": st.column_config.TextColumn("현재 담당"),
                "pingpong_count": st.column_config.ProgressColumn(
                    "핑퐁 횟수", min_value=0, max_value=max(r["pingpong_count"] for r in pingpong_rows), format="%d"
                ),
                "rule_id": st.column_config.TextColumn("규칙"),
            },
        )
        st.caption(f"핑퐁 발생 이벤트: {len(pingpong_rows)} / 전체 {len(rows)}건")
    else:
        st.caption("아직 핑퐁(재할당)이 발생한 이벤트가 없습니다.")

st.write("")
st.subheader("전체 이벤트 상태")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
