"""LiteLLM gateway, provider keys, tool-calling filter, and recorded cost."""

from __future__ import annotations

import inspect
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway import keys, llm, openai_gateway
from runtime.openhands import runner as openhands_runner
from store import db

from test_engine import client, fresh, ready, wait_status  # noqa: F401


SECRET = "sk" + "-" + "testvalueABCDEFG1234"


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
    openai_gateway.complete(
        "models/gemini-3.1-pro-preview",
        [{"role": "user", "content": "hi"}],
        [],
        {},
        provider="gemini",
    )
    assert seen[0] == "openai/gpt-4o"
    assert seen[1] == "gemini/gemini-2.0-flash"
    assert seen[2] == "gemini/gemini-3.1-pro-preview"
    assert llm.routed_model("gemini", "models/gemini-3.1-pro-preview") == "gemini/gemini-3.1-pro-preview"
    assert llm.stored_model_id("models/gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"


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


def test_gemini_list_ids_lose_models_prefix(monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr(
        "litellm.get_valid_models",
        lambda **kwargs: ["models/gemini-3.1-pro-preview", "models/gemini-2.0-flash-preview-image-generation"],
    )
    seen: list[tuple[str, str | None]] = []

    def check(*, model, custom_llm_provider=None):
        seen.append((model, custom_llm_provider))
        return "gemini-3.1-pro-preview" in model

    monkeypatch.setattr("litellm.supports_function_calling", check)
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: "k")
    names = llm.list_live_models("gemini")
    assert names == ["gemini-3.1-pro-preview"]
    assert seen == [("gemini/gemini-3.1-pro-preview", "gemini")]


def test_backup_model_uses_the_same_mapping(monkeypatch):
    seen: list[str] = []

    def fake_completion(**kwargs):
        seen.append(kwargs["model"])
        if kwargs["model"].startswith("openai/"):
            from litellm.exceptions import Timeout

            raise Timeout("timeout", llm_provider="openai", model=kwargs["model"])
        return _response("backup")

    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setattr(llm, "cost_usd", lambda *args, **kwargs: 0.01)
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: "k")
    monkeypatch.setattr("gateway.llm.time.sleep", lambda *_args, **_kwargs: None)
    turn = openai_gateway.complete(
        "gpt-4o",
        [{"role": "user", "content": "hi"}],
        [],
        {},
        provider="openai",
        backup_model={"provider": "gemini", "name": "models/gemini-3.1-pro-preview"},
    )
    assert seen[0] == "openai/gpt-4o"
    assert seen[-1] == "gemini/gemini-3.1-pro-preview"
    assert turn["backupUsed"] is True
    assert turn["actualModel"]["name"] == "gemini-3.1-pro-preview"


def test_openhands_uses_the_same_mapping():
    agent = {
        "model": {"provider": "gemini", "name": "models/gemini-3.1-pro-preview"},
        "backupModel": {"provider": "openai", "name": "gpt-4.1-mini"},
    }
    assert openhands_runner._model_id(agent) == "gemini/gemini-3.1-pro-preview"
    assert openhands_runner._backup_id(agent) == "openai/gpt-4.1-mini"


def test_cost_lookup_uses_mapped_name(monkeypatch):
    seen: list[str] = []

    def fake_cost(**kwargs):
        seen.append(kwargs["model"])
        return 0.02

    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.setattr("litellm.completion_cost", fake_cost)
    usd = llm.cost_usd(llm.routed_model("gemini", "models/gemini-3.1-pro-preview"), {"input_tokens": 1, "output_tokens": 1})
    assert seen == ["gemini/gemini-3.1-pro-preview"]
    assert usd == 0.02


def test_models_endpoint_shows_clean_gemini_ids(client):
    db.put("model-cache", "gemini", {"ids": ["models/gemini-3.1-pro-preview"]})
    rows = {item["name"]: item for item in client.get("/models").json()}
    assert "gemini-3.1-pro-preview" in rows
    assert rows["gemini-3.1-pro-preview"]["provider"] == "gemini"
    assert "models/gemini-3.1-pro-preview" not in rows


def test_agent_save_and_migration_strip_models_prefix(client):
    created = client.post(
        "/agents",
        json={
            "name": "Lead",
            "roleKey": "team-lead",
            "model": {"provider": "gemini", "name": "models/gemini-3.1-pro-preview", "config": {}},
            "backupModel": {"provider": "openai", "name": "models/gpt-4.1-mini", "config": {}},
        },
    ).json()
    assert created["model"]["name"] == "gemini-3.1-pro-preview"
    assert created["backupModel"]["name"] == "gpt-4.1-mini"
    agent = db.get("agent", created["id"])
    agent["model"]["name"] = "models/gemini-3.1-pro-preview"
    agent["backupModel"]["name"] = "models/gpt-4.1-mini"
    db.put("agent", created["id"], agent)
    db.put("model-cache", "gemini", {"ids": ["models/gemini-3.1-pro-preview"]})
    db.sync_stored_model_ids()
    saved = db.get("agent", created["id"])
    assert saved["model"]["name"] == "gemini-3.1-pro-preview"
    assert saved["backupModel"]["name"] == "gpt-4.1-mini"
    assert db.get("model-cache", "gemini")["ids"] == ["gemini-3.1-pro-preview"]


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="Set RUN_REAL_LLM_TESTS=1 for live Gemini")
def test_real_gemini_tiny_prompt(monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "0")
    token = keys.load("gemini")
    if not token:
        live = Path.home() / ".atelier-projects"
        if (live / ".secrets" / "providers" / "gemini.enc").is_file():
            monkeypatch.setenv("PROJECTS_DIR", str(live))
            keys._KNOWN.pop("gemini", None)
            token = keys.load("gemini")
    if not token:
        pytest.skip("Gemini key is not in the encrypted store")
    turn = llm.complete(
        "models/gemini-3.1-pro-preview",
        [{"role": "user", "content": "Reply with the single word pong."}],
        [],
        {},
        provider="gemini",
    )
    assert (turn.get("content") or "").strip()


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
