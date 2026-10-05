import sys
from pathlib import Path

# Streamlit executes each page as its own standalone script, so make sure
# the project root is importable as `src...` regardless of the launch cwd
# (sys.path[0] otherwise depends on how/where `streamlit run` was invoked).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from src.dashboard.common import DEPT_COLORS, dept_badge, inject_theme

st.set_page_config(page_title="부서 관리", page_icon="🗂️", layout="wide")
inject_theme()

st.markdown('<p class="hp-eyebrow">DEPARTMENT DIRECTORY · EXAMPLE DATA</p>', unsafe_allow_html=True)
st.title("부서 관리")
st.caption(
    "부서별 대표 연락처와 담당 인원 현황입니다. 아래 인원 정보는 실제 조직도가 "
    "연동되기 전까지 사용하는 예시 데이터로, 실제 운영 시에는 사내 인사 시스템과 "
    "연동해 교체해야 합니다."
)

# Example/placeholder data only -- no real personnel records. Keyed on the
# same four departments used everywhere else in this dashboard
# (src/dashboard/common.py's DEPT_COLORS / src/handover/tracker.py's
# VALID_DEPTS), so badge colors stay consistent with the other pages.
DEPT_DIRECTORY: dict[str, dict] = {
    "YI": {
        "full_name": "수율분석팀 (Yield & Inspection)",
        "contact": "내선 1200 · yi-team@fab-example.com",
        "members": [
            {"이름": "김도현", "직급": "팀장", "연락처": "010-1234-5601", "이메일": "dohyun.kim@fab-example.com"},
            {"이름": "이서연", "직급": "선임연구원", "연락처": "010-1234-5602", "이메일": "seoyeon.lee@fab-example.com"},
            {"이름": "박민재", "직급": "사원", "연락처": "010-1234-5603", "이메일": "minjae.park@fab-example.com"},
        ],
    },
    "MFG": {
        "full_name": "제조팀 (Manufacturing)",
        "contact": "내선 1300 · mfg-team@fab-example.com",
        "members": [
            {"이름": "최지훈", "직급": "팀장", "연락처": "010-2234-5601", "이메일": "jihoon.choi@fab-example.com"},
            {"이름": "정수아", "직급": "책임연구원", "연락처": "010-2234-5602", "이메일": "sua.jung@fab-example.com"},
            {"이름": "한예준", "직급": "선임연구원", "연락처": "010-2234-5603", "이메일": "yejun.han@fab-example.com"},
            {"이름": "오하은", "직급": "사원", "연락처": "010-2234-5604", "이메일": "haeun.oh@fab-example.com"},
        ],
    },
    "M-ENG": {
        "full_name": "설비기술팀 (Mechanical/Equipment Engineering)",
        "contact": "내선 1400 · meng-team@fab-example.com",
        "members": [
            {"이름": "강태민", "직급": "팀장", "연락처": "010-3234-5601", "이메일": "taemin.kang@fab-example.com"},
            {"이름": "윤소율", "직급": "선임연구원", "연락처": "010-3234-5602", "이메일": "soyul.yoon@fab-example.com"},
            {"이름": "임도윤", "직급": "사원", "연락처": "010-3234-5603", "이메일": "doyoon.lim@fab-example.com"},
        ],
    },
    "P-ENG": {
        "full_name": "공정기술팀 (Process Engineering)",
        "contact": "내선 1500 · peng-team@fab-example.com",
        "members": [
            {"이름": "서은우", "직급": "팀장", "연락처": "010-4234-5601", "이메일": "eunwoo.seo@fab-example.com"},
            {"이름": "문가은", "직급": "책임연구원", "연락처": "010-4234-5602", "이메일": "gaeun.moon@fab-example.com"},
            {"이름": "배지호", "직급": "선임연구원", "연락처": "010-4234-5603", "이메일": "jiho.bae@fab-example.com"},
            {"이름": "신아린", "직급": "사원", "연락처": "010-4234-5604", "이메일": "arin.shin@fab-example.com"},
        ],
    },
}

for dept in DEPT_COLORS:
    info = DEPT_DIRECTORY[dept]
    with st.container(border=True):
        header_col, contact_col = st.columns([3, 2])
        with header_col:
            st.markdown(dept_badge(dept) + f" &nbsp; **{info['full_name']}**", unsafe_allow_html=True)
        with contact_col:
            st.markdown(f"📞 {info['contact']}")

        st.dataframe(
            pd.DataFrame(info["members"]),
            width="stretch",
            hide_index=True,
            column_order=["이름", "직급", "연락처", "이메일"],
        )
    st.write("")
