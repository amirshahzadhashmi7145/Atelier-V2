"""LiteLLM gateway, provider keys, tool-calling filter, and recorded cost."""

from __future__ import annotations

import inspect
import json
import logging
from types import SimpleNamespace

from gateway import keys, llm, openai_gateway
from store import db

from test_engine import client, fresh, ready, wait_status  # noqa: F401


SECRET = "sk-secret-value-ABCDEFG1234"


def _response(text="ok", prompt=3, completion=5):
    message = SimpleNamespace(content=text, tool_calls=None)
    choice = SimpleNamespace(message=message, delta=SimpleNamespace(content=text, tool_calls=None))
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return SimpleNamespace(choices=[choice], usage=usage)


def test_gateway_signature_has_no_role():
    for fn in (llm.complete, llm.stream_turn, llm.iter_live_events):
        params = inspect.signature(fn).parameters
        assert "role" not in params
        assert "roleKey" not in params
        assert "kind" not in params


def test_gateway_routes_openai_and_gemini(monkeypatch):
    seen: list[str] = []

    def fake_completion(**kwargs):
        seen.append(kwargs["model"])
        assert kwargs.get("api_key") != SECRET
        return _response()

    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setattr(llm, "cost_usd", lambda *args, **kwargs: 0.01)
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: "k-not-logged")
    openai_gateway.complete("gpt-4o", [{"role": "user", "content": "hi"}], [], {}, provider="openai")
    openai_gateway.complete("gemini-2.0-flash", [{"role": "user", "content": "hi"}], [], {}, provider="gemini")
    assert seen[0].startswith("openai/")
    assert seen[1].startswith("gemini/")


def test_gateway_same_for_worker_and_supervisor(monkeypatch):
    seen: list[str] = []

    def fake_completion(**kwargs):
        seen.append(kwargs["model"])
        return _response()

    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setattr(llm, "cost_usd", lambda *args, **kwargs: 0.01)
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: "k")
    worker = [{"role": "user", "content": "build the page"}]
    supervisor = [{"role": "user", "content": "review the diff"}]
    openai_gateway.complete("gpt-4.1-mini", worker, [], {}, provider="openai", run_id="run_worker")
    openai_gateway.complete("gpt-4.1-mini", supervisor, [], {}, provider="openai", run_id="run_lead")
    assert seen == ["openai/gpt-4.1-mini", "openai/gpt-4.1-mini"]
    assert llm.routed_model("openai", "gpt-4.1-mini") == "openai/gpt-4.1-mini"


def test_provider_key_is_masked_and_not_returned(client, caplog):
    caplog.set_level(logging.DEBUG)
    saved = client.put("/providers/openai", json={"apiKey": SECRET})
    assert saved.status_code == 200
    body = saved.json()
    dumped = json.dumps(body)
    assert SECRET not in dumped
    assert body["keyHint"]
    assert SECRET not in body["keyHint"]
    assert body["keyRef"] == "secret:openai"
    listed = json.dumps(client.get("/providers").json())
    assert SECRET not in listed
    assert SECRET not in caplog.text
    raw = keys.path_for("openai").read_bytes()
    assert SECRET.encode() not in raw
    removed = client.delete("/providers/openai/key")
    assert removed.status_code == 200
    assert removed.json()["keyRef"] != "secret:openai"
    assert SECRET not in json.dumps(removed.json())


def test_tool_calling_filter(monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr("litellm.get_valid_models", lambda **kwargs: ["gpt-4o", "davinci-002", "whisper-1"])

    def check(*, model, custom_llm_provider=None):
        return "gpt-4o" in model

    monkeypatch.setattr("litellm.supports_function_calling", check)
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: "k")
    names = llm.list_live_models("openai")
    assert names == ["gpt-4o"]


def test_cost_recorded_per_run_agent_and_role(client):
    agent_id = ready(client)
    openai_gateway.SCRIPTS.append(
        {"content": "done", "tool_calls": [], "usage": {"input_tokens": 100, "output_tokens": 50}}
    )
    run = client.post(
        "/runs",
        json={"agentId": agent_id, "workspace": {"kind": "scaffold", "template": "local"}, "task": "Build"},
    ).json()
    finished = wait_status(client, run["id"], {"completed", "failed"})
    assert finished["status"] == "completed"
    assert finished["costUsd"] > 0
    agent_spend = db.get("agent-spend", agent_id)
    assert agent_spend and agent_spend["usd"] > 0 and agent_spend["calls"] >= 1
    role_spend = db.get("role-spend", "frontend")
    assert role_spend and role_spend["usd"] > 0
    assert abs(agent_spend["usd"] - role_spend["usd"]) < 0.0001


def test_spend_cap_uses_recorded_cost(client, monkeypatch):
    monkeypatch.setattr(llm, "cost_usd", lambda *args, **kwargs: 9.99)
    client.put("/settings/runs", json={"maxSpendPerRunUsd": 5, "maxIterations": 60, "maxMinutes": 45, "loopDetection": True})
    agent_id = ready(client)
    openai_gateway.SCRIPTS.append(
        {"content": "working", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    run = client.post(
        "/runs",
        json={"agentId": agent_id, "workspace": {"kind": "scaffold", "template": "local"}, "task": "Build"},
    ).json()
    finished = wait_status(client, run["id"], {"completed", "failed"})
    assert finished["status"] == "failed"
    assert finished.get("terminalCause") == "budget"
    assert finished["costUsd"] == 9.99


def test_role_fit_storage_is_keyed_by_role_id(client):
    saved = client.put("/role-fits/qa-engineer", json={"labels": ["careful", "cheap"]})
    assert saved.status_code == 200
    assert saved.json()["roleId"] == "qa-engineer"
    assert saved.json()["labels"] == ["careful", "cheap"]
    listed = client.get("/role-fits").json()
    assert any(item["roleId"] == "qa-engineer" for item in listed)


def test_no_openai_sdk_import_outside_tests():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    banned = []
    pattern = re.compile(r"^(?:from openai import|import openai)\b", re.M)
    for folder in ("app", "gateway", "runtime", "store"):
        for path in (root / folder).rglob("*.py"):
            if pattern.search(path.read_text()):
                banned.append(str(path.relative_to(root)))
    assert banned == []
