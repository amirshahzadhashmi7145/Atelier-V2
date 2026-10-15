import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gateway import gemini_transcript, mock_turns, openai_gateway
from gateway.providers import gemini as gemini_mod
from gateway.tool_pairing import ToolPairingError, assert_chat_tool_pairing

FIXTURE = Path(__file__).parent / "fixtures" / "gemini_recorded.json"


@pytest.fixture(autouse=True)
def mock_gateway(monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "1")
    monkeypatch.delenv("MOCK_GEMINI_PROVIDER_ERROR", raising=False)
    gemini_mod.last_contents_sent = None


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_gemini_recorded_fixture_streams():
    openai_gateway.SCRIPTS.clear()
    payload = _fixture()
    messages = payload["messages"]
    provider = gemini_mod.GeminiProvider()
    events = list(provider.complete("gemini-2.0-flash", messages, [], {}, stream=True))
    assert any(event["kind"] == "delta" for event in events)
    done = [event for event in events if event["kind"] == "done"][-1]
    assert done["content"] == payload["recorded"]["content"]
    assert done.get("gemini_model_content") == payload["recorded"]["gemini_model_content"]


def test_second_request_echoes_thought_signature():
    payload = _fixture()
    second = payload["second_request"]
    assert_chat_tool_pairing(second["messages"])
    provider = gemini_mod.GeminiProvider()
    list(provider.complete("gemini-2.0-flash", second["messages"], [], {}, stream=True))
    assert gemini_mod.last_contents_sent is not None
    model_turn = gemini_mod.last_contents_sent[1]
    parts = model_turn.parts if hasattr(model_turn, "parts") else []
    assert parts
    assert getattr(parts[0], "thought_signature", None) is not None
    stored = second["messages"][1]["gemini_model_content"]
    assert gemini_transcript.contents_include_stored_signatures(stored, parts)


def test_reconstructed_assistant_raises_thought_signature_lost():
    payload = _fixture()
    bad = list(payload["second_request"]["messages"])
    bad[1] = {
        "role": "assistant",
        "content": None,
        "tool_calls": bad[1]["tool_calls"],
    }
    with pytest.raises(ToolPairingError, match="thought_signature lost"):
        list(openai_gateway.stream_turn("gemini-2.0-flash", bad, [], {}, provider="gemini"))


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


def test_provider_error_fails_run_within_two_seconds(monkeypatch, tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ["PROJECTS_DIR"] = str(tmp_path / "projects")
    os.environ["GATEWAY_MOCK"] = "1"
    os.environ["FORCE_LOCAL"] = "1"
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ["MOCK_GEMINI_PROVIDER_ERROR"] = "INVALID_ARGUMENT: Function call is missing a thought_signature"
    from store import db

    db.reset_engine()
    mock_turns.SCRIPTS.clear()
    openai_gateway.begin()
    from app.main import app

    client = TestClient(app)
    agent = client.post(
        "/agents",
        json={
            "name": "Frontend",
            "roleKey": "frontend",
            "toolIds": ["files"],
            "model": {"provider": "gemini", "name": "gemini-2.0-flash", "config": {}},
        },
    ).json()
    version = client.post(
        f"/agents/{agent['id']}/versions",
        json={"sections": {"role": "R", "goal": "G", "instructions": "W", "constraints": "C", "output": "O"}},
    ).json()
    client.post(f"/agents/{agent['id']}/versions/{version['version']}/activate")
    started = time.time()
    run = client.post(
        "/runs",
        json={"agentId": agent["id"], "workspace": {"kind": "scaffold", "template": "local"}, "task": "hello"},
    ).json()
    while time.time() - started < 2:
        row = client.get(f"/runs/{run['id']}").json()
        if row["status"] == "failed":
            break
        time.sleep(0.05)
    assert time.time() - started < 2
    failed = client.get(f"/runs/{run['id']}").json()
    assert failed["status"] == "failed"
    events = db.events_for(run["id"])
    fail = next(item for item in events if item["type"] == "RUN_FAILED")
    assert "thought_signature" in fail["payload"]["text"]


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


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="Set RUN_REAL_LLM_TESTS=1 for live Gemini")
def test_real_connect_four_gemini(tmp_path):
    if not gemini_mod.api_key():
        pytest.skip("GEMINI_API_KEY not set")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/live.db"
    os.environ["PROJECTS_DIR"] = str(tmp_path / "projects")
    os.environ.pop("GATEWAY_MOCK", None)
    from store import db

    db.reset_engine()
    db.put("settings", "runs", {"recordModelRequests": True, "maxSpendPerRunUsd": 5})
    from app.main import app

    client = TestClient(app)
    agent = client.post(
        "/agents",
        json={
            "name": "Frontend",
            "roleKey": "frontend",
            "toolIds": ["files", "shell", "build_test", "headless_browser"],
            "model": {"provider": "gemini", "name": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "config": {}},
        },
    ).json()
    version = client.post(
        f"/agents/{agent['id']}/versions",
        json={"sections": {"role": "R", "goal": "G", "instructions": "W", "constraints": "C", "output": "O"}},
    ).json()
    client.post(f"/agents/{agent['id']}/versions/{version['version']}/activate")
    run = client.post(
        "/runs",
        json={
            "agentId": agent["id"],
            "workspace": {"kind": "scaffold", "template": "local"},
            "task": "Build a Connect 4 game UI with a playable board",
        },
    ).json()
    deadline = time.time() + 600
    while time.time() < deadline:
        row = client.get(f"/runs/{run['id']}").json()
        if row["status"] in ("completed", "failed"):
            break
        time.sleep(1)
    assert client.get(f"/runs/{run['id']}").json()["status"] == "completed"
    capture = Path(__file__).resolve().parents[1] / "debug" / "runs" / run["id"]
    assert capture.is_dir()
