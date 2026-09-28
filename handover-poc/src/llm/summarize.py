"""LLM-generated natural-language summary of one event's diagnosis, for
handover communication. Calls the Claude API (model: claude-opus-5) to
turn diagnosis.notes/contributions and handover history into a short
Korean paragraph a department can act on immediately -- it never
re-derives or overrides the diagnosis itself, only narrates it.

Credentials are resolved by the Anthropic SDK the normal way (env var,
`ant auth login` profile, etc.) -- this module never pre-checks
os.environ, since an unset ANTHROPIC_API_KEY doesn't mean there are no
credentials. If the SDK can't authenticate, that surfaces as a plain
RuntimeError with guidance, not a silently skipped summary.
"""
import anthropic

MODEL = "claude-opus-5"

SYSTEM_PROMPT = (
    "당신은 반도체 팹의 불량 대응 인수인계를 돕는 보조입니다. 아래 판정 결과를 "
    "부서 실무자가 빠르게 읽을 수 있는 한국어 요약으로 바꿔주세요.\n\n"
    "반드시 지켜야 할 규칙:\n"
    "- '판정 점수'를 '확률'이나 '신뢰도'라고 부르지 마세요. 이 점수는 근거 조합에 따른 "
    "상대 점수일 뿐, 확률이 아닙니다.\n"
    "- 이 데이터는 실제 팹 데이터가 아니라 시뮬레이션 데이터(is_simulated=true)입니다. "
    "요약에서 이 사실을 숨기거나 실제 사건처럼 서술하지 마세요.\n"
    "- 판정 근거(rule_id, notes, contributions)에 없는 새로운 원인을 추측해서 덧붙이지 "
    "마세요 -- 주어진 근거만 자연어로 정리하세요.\n"
    "- 3~5문장, 담당자가 바로 읽고 판단할 수 있는 실무 어투로 작성하세요."
)


def _build_user_message(event: dict, handovers: list[dict]) -> str:
    diagnosis = event["diagnosis"]
    signals = event["signals"]
    lines = [
        f"이벤트: {event['event_id']} (시나리오 {event['scenario_id']}, "
        f"is_simulated={event['is_simulated']})",
        f"규칙: {diagnosis['rule_id']}",
        f"주관 부서(생성 시점): {diagnosis['primary_dept']}",
        f"보조 부서: {', '.join(diagnosis['secondary_depts']) or '없음'}",
        f"MFG Hold: {diagnosis['mfg_hold']}",
        f"판정 점수: {diagnosis['scores']}",
        f"세부 기여도: {diagnosis['contributions']}",
    ]
    if diagnosis.get("notes"):
        lines.append("판정 노트: " + " / ".join(diagnosis["notes"]))
    lines.append(
        f"신호 요약: 비전={signals['vision']['pattern']}({signals['vision']['pattern_group']}), "
        f"센서 이상점수={signals['sensor']['anomaly_score']:.3f}, "
        f"진동 모드={signals['vibration']['mode']}"
    )
    if handovers:
        history_str = "; ".join(f"{h['from_dept']}->{h['to_dept']} ({h['reason']})" for h in handovers)
        lines.append(f"핑퐁 이력: {history_str}")
    else:
        lines.append("핑퐁 이력: 없음")
    return "\n".join(lines)


def summarize_diagnosis(event: dict, handovers: list[dict]) -> str:
    """Returns a short Korean summary of one event's diagnosis + handover
    history. Raises RuntimeError (with setup guidance) if the Claude API
    call can't authenticate; re-raises other anthropic errors as-is."""
    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            # Simple summarization of already-structured data (not open-ended
            # reasoning) -- low effort holds quality here at lower cost, per
            # this project's cost-conscious PoC scope.
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(event, handovers)}],
        )
    except anthropic.AuthenticationError as e:
        raise RuntimeError(
            "Claude API 인증 실패 -- ANTHROPIC_API_KEY 환경변수를 설정하거나 "
            "`ant auth login`으로 로그인하세요."
        ) from e

    return next(block.text for block in response.content if block.type == "text")
