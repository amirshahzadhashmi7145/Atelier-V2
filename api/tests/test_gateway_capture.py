import json
import os
from pathlib import Path

import pytest

from gateway import openai_gateway
from gateway.request_capture import DEBUG_ROOT
from store import db


@pytest.fixture(autouse=True)
def mock_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    db.reset_engine()
    openai_gateway.SCRIPTS.clear()
    openai_gateway.begin()
    db.put("settings", "runs", {"maxSpendPerRunUsd": 5, "maxIterations": 60, "maxMinutes": 45, "loopDetection": True, "recordModelRequests": True})
    yield


def test_chat_completions_fixture_records_redacted_request(tmp_path):
    openai_gateway.SCRIPTS.append({"content": "ok", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 1}})
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "files", "arguments": "{}"}}], "content": None},
        {"role": "tool", "tool_call_id": "t1", "content": "done"},
    ]
    list(openai_gateway.stream_turn("gpt-4.1-mini", messages, [], {}, run_id="run_cap", call_index=0))
    path = DEBUG_ROOT / "run_cap" / "0.json"
    assert path.exists()
    payload = json.loads(path.read_text())
    assert "request" in payload and "response" in payload
    fixture = Path(__file__).parent / "fixtures" / "chat_completions_recorded.json"
    fixture.parent.mkdir(exist_ok=True)
    fixture.write_text(json.dumps({"messages": messages, "recorded": payload}, indent=2))
