import sys
import tempfile
from pathlib import Path

# Streamlit executes each page as its own standalone script, so make sure
# the project root is importable as `src...` regardless of the launch cwd
# (sys.path[0] otherwise depends on how/where `streamlit run` was invoked).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from src.dashboard.common import dept_badge, get_db_path, inject_theme
from src.handover.tracker import VALID_DEPTS
from src.llm.summarize import summarize_diagnosis
from src.report.pdf import generate_handover_pdf
from src.storage import repository as repo

st.set_page_config(page_title="이벤트 상세", page_icon="🔍", layout="wide")
inject_theme()

st.markdown('<p class="hp-eyebrow">EVENT DETAIL</p>', unsafe_allow_html=True)
st.title("이벤트 상세")

db_path = get_db_path()

event_id = st.text_input("event_id", placeholder="EVT-...")
if not event_id:
    st.info("event_id를 입력하세요 (이벤트 목록 페이지에서 복사).")
    st.stop()

event = repo.get_event(db_path, event_id)
if event is None:
    st.error("해당 event_id를 찾을 수 없습니다.")
    st.stop()

diagnosis = event["diagnosis"]
signals = event["signals"]
history = repo.list_handovers(db_path, event_id)

title_col, dl_col = st.columns([5, 1])
with title_col:
    st.markdown(
        f"### `{event_id}` &nbsp; {dept_badge(diagnosis['primary_dept'])}",
        unsafe_allow_html=True,
    )
    badge_row = f"규칙 `{diagnosis['rule_id']}`"
    if diagnosis["mfg_hold"]:
        badge_row += " &nbsp;·&nbsp; 🔒 **MFG Hold**"
    st.caption(badge_row)
with dl_col:
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / f"{event_id}.pdf"
        generate_handover_pdf(event, history, pdf_path)
        pdf_bytes = pdf_path.read_bytes()
    st.download_button(
        "📄 PDF 다운로드",
        data=pdf_bytes,
        file_name=f"{event_id}.pdf",
        mime="application/pdf",
        width="stretch",
    )

st.write("")
col1, col2 = st.columns(2, gap="large")

with col1:
    with st.container(border=True):
        st.subheader("판정")
        st.write(f"**secondary_depts**: {', '.join(diagnosis['secondary_depts']) or '-'}")

        st.write("**scores** (판정 점수 — 확률이 아님):")
        s1, s2 = st.columns(2)
        s1.metric("equipment", f"{diagnosis['scores'].get('equipment', 0):.2f}")
        s2.metric("process", f"{diagnosis['scores'].get('process', 0):.2f}")
        st.bar_chart(diagnosis["scores"])

        st.write("**contributions** (가설별 세부 항목):")
        for hyp, contrib in diagnosis["contributions"].items():
            st.caption(f"`{hyp}`")
            st.json(contrib, expanded=True)

        if diagnosis.get("notes"):
            st.write("**notes**:")
            for n in diagnosis["notes"]:
                st.caption(f"— {n}")

with col2:
    with st.container(border=True):
        st.subheader("신호 (signals)")
        st.json(signals, expanded=2)
        if event.get("_notes"):
            st.write("**_notes** (샘플링 시 스킵된 조건 등):")
            for n in event["_notes"]:
                st.caption(f"— {n}")

st.write("")
with st.container(border=True):
    st.subheader("🤖 AI 요약")
    st.caption("Claude API로 위 판정 근거를 실무자용 한국어 요약으로 정리합니다 (판정 자체를 바꾸지 않음).")
    summary_key = f"summary_{event_id}"
    if st.button("요약 생성", key="summary_button"):
        try:
            with st.spinner("요약 생성 중..."):
                st.session_state[summary_key] = summarize_diagnosis(event, history)
        except RuntimeError as e:
            st.warning(str(e))
    if summary_key in st.session_state:
        st.write(st.session_state[summary_key])

st.write("")
st.divider()
st.subheader("핑퐁 이력")

current_dept = history[-1]["to_dept"] if history else diagnosis["primary_dept"]

m1, m2 = st.columns(2)
with m1:
    st.markdown("**현재 담당 부서**")
    st.markdown(dept_badge(current_dept), unsafe_allow_html=True)
m2.metric("핑퐁 횟수", len(history))

if history:
    st.write("")
    for h in history:
        with st.container(border=True):
            st.markdown(
                f"{dept_badge(h['from_dept'])} &nbsp;→&nbsp; {dept_badge(h['to_dept'])}"
                f"&nbsp;&nbsp;<span style='color:#898781; font-size:0.85rem;'>{h['created_at']}</span>",
                unsafe_allow_html=True,
            )
            st.write(h["reason"])
else:
    st.caption("아직 재할당 이력이 없습니다.")

st.write("")
with st.container(border=True):
    st.subheader("재할당 기록")
    candidates = [d for d in VALID_DEPTS if d != current_dept]
    with st.form("handover_form"):
        to_dept = st.selectbox("담당 부서로 재할당", candidates)
        reason = st.text_area("이유 (필수)")
        submitted = st.form_submit_button("재할당", type="primary")
        if submitted:
            try:
                repo.add_handover(db_path, event_id, to_dept, reason)
                st.success("재할당이 기록되었습니다.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
