import copy
import sys
from pathlib import Path

# Streamlit executes each page as its own standalone script, so make sure
# the project root is importable as `src...` regardless of the launch cwd
# (sys.path[0] otherwise depends on how/where `streamlit run` was invoked).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
import streamlit as st

from src.dashboard.common import get_ctx, get_rules, inject_theme

st.set_page_config(page_title="규칙 튜닝", page_icon="⚙️", layout="wide")
inject_theme()

st.markdown('<p class="hp-eyebrow">RULE TUNING · PREVIEW ONLY</p>', unsafe_allow_html=True)
st.title("운영자용 규칙 튜닝")
st.caption(
    "여기서 바꾼 값은 config/rules.yaml에 저장되지 않습니다 — 주석이 달린 yaml을 "
    "자동으로 덮어써서 날리지 않기 위한 설계입니다. 마음에 드는 값이 나오면 "
    "rules.yaml에 직접 옮겨 적으세요."
)

ctx = get_ctx()
base_rules = get_rules()
rules = copy.deepcopy(base_rules)

col1, col2 = st.columns(2, gap="large")
with col1:
    with st.container(border=True):
        st.subheader("임계값 (thresholds)")
        t = rules["thresholds"]
        t["score_min"] = st.slider("score_min (R2: 최고 가설 최소 점수)", 0.0, 1.0, t["score_min"], 0.01)
        t["score_gap_min"] = st.slider("score_gap_min (R2: 1·2위 점수 차)", 0.0, 1.0, t["score_gap_min"], 0.01)
        t["sensor_low"] = st.slider("sensor_low (R0: 센서 이상 낮음 기준)", 0.0, 1.0, t["sensor_low"], 0.01)
        t["abnormality_low_max"] = st.slider(
            "abnormality_low_max (R0: 진동 calm 기준)", 0.0, 1.0, t["abnormality_low_max"], 0.01
        )

with col2:
    with st.container(border=True):
        st.subheader("가중치 (weights)")
        eq = rules["weights"]["equipment"]
        pr = rules["weights"]["process"]
        st.caption("equipment 가설")
        eq["edge_pattern"] = st.slider("equipment.edge_pattern", 0.0, 1.0, eq["edge_pattern"], 0.05)
        eq["vibration_abnormal"] = st.slider(
            "equipment.vibration_abnormal", 0.0, 1.0, eq["vibration_abnormal"], 0.05
        )
        eq["sensor_normal"] = st.slider("equipment.sensor_normal", 0.0, 1.0, eq["sensor_normal"], 0.05)
        st.caption("process 가설")
        pr["center_pattern"] = st.slider("process.center_pattern", 0.0, 1.0, pr["center_pattern"], 0.05)
        pr["sensor_anomaly"] = st.slider("process.sensor_anomaly", 0.0, 1.0, pr["sensor_anomaly"], 0.05)
        pr["vibration_normal"] = st.slider("process.vibration_normal", 0.0, 1.0, pr["vibration_normal"], 0.05)

st.write("")
seeds = st.number_input("시나리오당 시드 수 (미리보기, 클수록 느려짐)", min_value=5, max_value=200, value=30, step=5)

if st.button("이 설정으로 재실행", type="primary"):
    from experiments.run_batch import compute_batch_results

    with st.spinner("재실행 중..."):
        result = compute_batch_results(ctx, rules, int(seeds))

    scenario_ids = result["scenario_ids"]
    per_total = result["per_scenario_total"]
    per_correct = result["per_scenario_correct"]

    overall_total = sum(per_total.values())
    overall_correct = sum(per_correct.values())
    overall_acc = (overall_correct / overall_total) if overall_total else 0.0

    st.write("")
    st.metric("전체 정확도", f"{overall_acc:.1%}")

    st.subheader("시나리오별 정확도")
    acc_rows = [
        {
            "scenario_id": s,
            "correct": per_correct[s],
            "total": per_total[s],
            "accuracy": (per_correct[s] / per_total[s]) if per_total[s] else 0.0,
        }
        for s in scenario_ids
    ]
    st.dataframe(
        acc_rows,
        use_container_width=True,
        hide_index=True,
        column_config={"accuracy": st.column_config.ProgressColumn("정확도", min_value=0.0, max_value=1.0, format="%.0f%%")},
    )

    st.subheader("혼동행렬")
    confusion_df = pd.DataFrame(
        [{"expected_dept": e, "predicted_dept": p, "count": c} for (e, p), c in result["confusion"].items()]
    )
    pivot = confusion_df.pivot_table(
        index="expected_dept", columns="predicted_dept", values="count", fill_value=0, aggfunc="sum"
    )
    st.dataframe(pivot, use_container_width=True)
    st.caption("행 = 정답(expected_dept), 열 = 판정 결과(predicted_dept)")

    st.info("이 결과는 미리보기이며 DB나 파일에 저장되지 않았습니다.")
