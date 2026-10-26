"""The chat reply must give the model the whole conversation when the user asks for
a summary, not just the last few turns (otherwise it can only recap the tail)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime import classify
from store import db

from test_engine import client, fresh  # noqa: F401
from test_s17_openhands import _agent  # noqa: F401


def _seed_messages(project_id: str, count: int) -> None:
    for i in range(count):
        mid = db.nid("msg")
        db.put(
            "message",
            mid,
            {
                "id": mid,
                "projectId": project_id,
                "role": "user" if i % 2 == 0 else "agent",
                "text": f"message number {i}",
                "createdAt": f"2026-01-01T00:{i:02d}:00.000Z",
            },
        )


def test_summary_request_includes_old_messages(client: TestClient, monkeypatch):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "History", "agentId": agent["id"]}).json()
    _seed_messages(project["id"], 30)

    captured: dict[str, str] = {}

    def fake_complete(model, messages, tools, opts, provider=None):
        captured["prompt"] = messages[-1]["content"]
        return {"content": "ok"}

    # Bypass the mock short-circuit so the real history-building path runs.
    monkeypatch.delenv("GATEWAY_MOCK", raising=False)
    monkeypatch.setattr(openai_gateway, "complete", fake_complete)

    classify.chat_reply(agent, "please give me a summary of the whole conversation", project["id"])
    prompt = captured["prompt"]
    # The earliest messages must be present for a summary ask (window widened to all).
    assert "message number 0" in prompt
    assert "message number 29" in prompt


def test_plain_reply_only_includes_recent_messages(client: TestClient, monkeypatch):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "History2", "agentId": agent["id"]}).json()
    _seed_messages(project["id"], 60)

    captured: dict[str, str] = {}

    def fake_complete(model, messages, tools, opts, provider=None):
        captured["prompt"] = messages[-1]["content"]
        return {"content": "ok"}

    monkeypatch.delenv("GATEWAY_MOCK", raising=False)
    monkeypatch.setattr(openai_gateway, "complete", fake_complete)

    classify.chat_reply(agent, "what is next?", project["id"])
    prompt = captured["prompt"]
    # A normal reply uses only the recent window, so very old messages are excluded.
    assert "message number 0" not in prompt
    assert "message number 59" in prompt
