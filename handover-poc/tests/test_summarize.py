"""Tests for src/llm/summarize.py. No real network calls -- the Anthropic
client is mocked throughout, matching how the rest of this project keeps
tests offline (synthetic SamplingContext, no real SECOM/WM-811K needed).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.llm.summarize import MODEL, SYSTEM_PROMPT, _build_user_message, summarize_diagnosis


def _sample_event() -> dict:
    return {
        "event_id": "EVT-1",
        "scenario_id": "SC-EQ",
        "seed": 1,
        "is_simulated": True,
        "signals": {
            "vision": {"pattern": "Edge-Ring", "pattern_group": "edge"},
            "sensor": {"anomaly_score": 0.42},
            "vibration": {"mode": "single_file"},
        },
        "diagnosis": {
            "rule_id": "R2",
            "primary_dept": "M-ENG",
            "secondary_depts": ["P-ENG"],
            "mfg_hold": True,
            "scores": {"equipment": 0.7, "process": 0.2},
            "contributions": {"equipment": {"edge_pattern": 0.4}},
            "notes": ["some diagnostic note"],
        },
    }


def test_build_user_message_includes_key_fields():
    msg = _build_user_message(_sample_event(), handovers=[])

    assert "EVT-1" in msg
    assert "is_simulated=True" in msg
    assert "R2" in msg
    assert "M-ENG" in msg
    assert "핑퐁 이력: 없음" in msg


def test_build_user_message_includes_handover_history():
    handovers = [{"from_dept": "M-ENG", "to_dept": "P-ENG", "reason": "설비 이상 없음"}]
    msg = _build_user_message(_sample_event(), handovers=handovers)

    assert "M-ENG->P-ENG" in msg
    assert "설비 이상 없음" in msg


def test_system_prompt_forbids_confidence_language():
    """Static guard: the constraint text must survive future edits -- this
    is the same rigor the diagnosis engine itself enforces in its scores."""
    assert "확률" in SYSTEM_PROMPT
    assert "신뢰도" in SYSTEM_PROMPT
    assert "is_simulated" in SYSTEM_PROMPT


def test_summarize_diagnosis_calls_api_with_expected_params_and_returns_text():
    fake_response = SimpleNamespace(content=[SimpleNamespace(type="text", text="요약문입니다.")])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response

    with patch("src.llm.summarize.anthropic.Anthropic", return_value=mock_client):
        result = summarize_diagnosis(_sample_event(), handovers=[])

    assert result == "요약문입니다."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == MODEL
    assert call_kwargs["system"] == SYSTEM_PROMPT
    assert call_kwargs["output_config"] == {"effort": "low"}
    assert "EVT-1" in call_kwargs["messages"][0]["content"]


def test_summarize_diagnosis_raises_runtime_error_on_authentication_failure():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = anthropic.AuthenticationError(
        "invalid api key", response=MagicMock(), body=None
    )

    with patch("src.llm.summarize.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            summarize_diagnosis(_sample_event(), handovers=[])
