"""Streamlit dashboard entry point.

Run with: streamlit run src/dashboard/메인페이지.py

Pages live in src/dashboard/pages/ (Streamlit auto-discovers that folder
next to this script and lists them in the sidebar). The file is named
메인페이지.py (rather than app.py) because Streamlit's legacy multipage nav
derives the sidebar label directly from the script's filename -- there is
no separate "nav title" setting for the entry script, only st.set_page_config's
page_title (browser tab only). Renaming the file is the supported way to
control that label.
"""
import sys
from pathlib import Path

# Make sure the project root is importable as `src...` regardless of the
# launch cwd (sys.path[0] otherwise depends on how/where `streamlit run`
# was invoked). 메인페이지.py sits at src/dashboard/메인페이지.py -- two levels
# below the project root (parents[2]), unlike pages/*.py which are three
# levels down (parents[3]) -- mixing these up is exactly the bug a real-data
# smoke test caught here: it silently inserted the *parent* of the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from src.dashboard.common import dept_badge, get_db_path, inject_theme
from src.storage import repository as repo

st.set_page_config(page_title="반도체 불량 대응 인수인계", page_icon="🏭", layout="wide")
inject_theme()

st.markdown('<p class="hp-eyebrow">SEMICONDUCTOR HANDOVER POC</p>', unsafe_allow_html=True)
st.title("반도체 불량 대응 인수인계 대시보드")
st.caption(
    "웨이퍼 비전 · 공정 센서 · 설비 진동 신호를 규칙 기반으로 판정해 주관 부서를 제안하고, "
    "부서 간 재할당(\"핑퐁\")을 추적합니다."
)

st.divider()

db_path = get_db_path()
rows = repo.list_events_with_status(db_path, limit=5000)

total = len(rows)
pingpong = sum(1 for r in rows if r["pingpong_count"] > 0)
mfg_hold = sum(1 for r in rows if r["mfg_hold"])

col1, col2, col3 = st.columns(3)
col1.metric("전체 이벤트", f"{total:,}")
col2.metric("핑퐁 발생 이벤트", f"{pingpong:,}", help="한 번 이상 재할당된 이벤트 수")
col3.metric("MFG Hold", f"{mfg_hold:,}", help="비전 신호에서 웨이퍼 결함이 감지된 이벤트 수")

if rows:
    st.write("**부서별 현재 담당 현황**")
    badges = " ".join(
        dept_badge(dept) + f" &nbsp;{sum(1 for r in rows if (r['current_dept'] or None) == dept)}건 &nbsp;&nbsp; "
        for dept in ["YI", "MFG", "M-ENG", "P-ENG"]
    )
    st.markdown(badges, unsafe_allow_html=True)

st.divider()

st.markdown(
    """
    ##### 페이지 안내
    - **① 이벤트 목록** — 생성된 이벤트 조회/필터 + 새 이벤트 생성
    - **② 이벤트 상세** — 신호·판정 근거·핑퐁 이력 확인, 재할당 기록
    - **③ 부서 현황** — 부서별 현재 담당 건수, 핑퐁 랭킹
    - **④ 규칙 튜닝** — 판정 가중치/임계값을 바꿔보고 정확도 미리보기 (파일에는 저장되지 않음)
    - **⑤ 부서 관리** — 부서별 연락처 및 담당 인원 현황

    좌측 사이드바에서 페이지를 선택하세요. 데이터가 없다면 "이벤트 목록" 페이지에서 먼저
    이벤트를 생성하세요. CLI/API와 같은 `src.storage.repository`/`src.cli.build_event`를
    직접 호출합니다 (별도 서버 실행 불필요).
    """
)
