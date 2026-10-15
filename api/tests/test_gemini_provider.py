import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from gateway import openai_gateway
from gateway.providers import gemini as gemini_mod
from gateway.providers.registry import get
from gateway.tool_pairing import ToolPairingError, assert_chat_tool_pairing


@pytest.fixture(autouse=True)
def mock_gateway(monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "1")


def test_gemini_recorded_fixture_streams():
    openai_gateway.SCRIPTS.clear()
    fixture = Path(__file__).parent / "fixtures" / "gemini_recorded.json"
    payload = json.loads(fixture.read_text())
    messages = payload["messages"]
    assert_chat_tool_pairing(messages)
    provider = gemini_mod.GeminiProvider()
    events = list(provider.complete("gemini-2.0-flash", messages, [], {}, stream=True))
    assert any(event["kind"] == "delta" for event in events)
    done = [event for event in events if event["kind"] == "done"][-1]
    assert done["content"] == payload["recorded"]["content"]


def test_pairing_rejects_orphan_tool_on_gemini_path():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "files", "arguments": "{}"}}], "content": None},
    ]
    with pytest.raises(ToolPairingError):
        list(openai_gateway.stream_turn("gemini-2.0-flash", messages, [], {}, provider="gemini"))


def test_config_schema_thinking_family():
    schema = gemini_mod.GeminiProvider().config_schema("gemini-2.5-pro")
    assert "thinkingBudget" in schema["properties"]
    flash = gemini_mod.GeminiProvider().config_schema("gemini-2.0-flash")
    assert "maxOutputTokens" in flash["properties"]


def test_list_models_filters_non_chat():
    provider = gemini_mod.GeminiProvider()
    ids = provider.list_models()
    assert all("gemini" in name for name in ids)
    assert not any("embedding" in name for name in ids)


def test_timeout_on_stalled_stream(monkeypatch):
    monkeypatch.setenv("MOCK_MODEL_HANG", "1")
    monkeypatch.setenv("MODEL_FIRST_TOKEN_S", "0.05")
    provider = gemini_mod.GeminiProvider()
    with pytest.raises(Exception) as exc:
        list(provider.complete("gemini-2.0-flash", [{"role": "user", "content": "hi"}], [], {}, stream=True))
    assert "timed out" in str(exc.value).lower()


def test_gateway_timeout_message():
    msg = openai_gateway._timeout_message("gemini", "gemini-2.5-flash")
    assert msg == "model call timed out (gemini/gemini-2.5-flash)"


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="Set RUN_REAL_LLM_TESTS=1 for live Gemini")
def test_real_tic_tac_toe_gemini():
    if not gemini_mod.api_key():
        pytest.skip("GEMINI_API_KEY not set")
    openai_gateway.SCRIPTS.clear()
    turn = openai_gateway.complete(
        os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        [{"role": "user", "content": "make a tic tac toe UI"}],
        [],
        {},
        provider="gemini",
    )
    assert turn.get("content") or turn.get("tool_calls")


def test_list_models_live_pattern_filter(monkeypatch):
    class FakeModel:
        def __init__(self, name, actions):
            self.name = name
            self.supported_actions = actions

    class FakeClient:
        class models:
            @staticmethod
            def list():
                return [
                    FakeModel("models/gemini-2.0-flash", ["generateContent"]),
                    FakeModel("models/text-embedding-004", ["embedContent"]),
                    FakeModel("models/gemini-2.5-pro", ["generateContent"]),
                ]

    monkeypatch.delenv("GATEWAY_MOCK", raising=False)
    with patch.object(gemini_mod.GeminiProvider, "_client", return_value=FakeClient()):
        ids = gemini_mod.GeminiProvider().list_models()
    assert "gemini-2.0-flash" in ids
    assert "text-embedding-004" not in ids
