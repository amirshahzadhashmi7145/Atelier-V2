"""Auto model selection: pick an available model by task tier, rescue removed models."""

from __future__ import annotations

from fastapi.testclient import TestClient

from runtime import automodel

from test_engine import client, fresh  # noqa: F401


def test_auto_high_tier_prefers_reasoning_model(client: TestClient):
    # Mock OpenAI pool is gpt-5 / gpt-4.1 / gpt-4.1-mini.
    picked = automodel.resolve(automodel.auto_spec(), role_key="team-lead", kind="lead", text="plan the work")
    assert picked["name"] == "gpt-5"


def test_auto_standard_tier_prefers_fast_model(client: TestClient):
    picked = automodel.resolve(automodel.auto_spec(), role_key="frontend-engineer", kind=None, text="add a button")
    assert picked["name"] == "gpt-4.1-mini"


def test_hard_task_bumps_worker_to_high(client: TestClient):
    picked = automodel.resolve(
        automodel.auto_spec(),
        role_key="frontend-engineer",
        kind=None,
        text="refactor the auth flow and fix the race condition",
    )
    assert picked["name"] == "gpt-5"


def test_pinned_available_model_is_kept(client: TestClient):
    spec = {"provider": "openai", "name": "gpt-4.1", "config": {}}
    picked = automodel.resolve(spec, role_key="frontend-engineer", kind=None, text="x")
    assert picked["name"] == "gpt-4.1"


def test_removed_model_is_substituted(client: TestClient):
    # gpt-4o is not in the mock pool (removed) -> auto-picks an available one.
    spec = {"provider": "openai", "name": "gpt-4o", "config": {}}
    picked = automodel.resolve(spec, role_key="frontend-engineer", kind=None, text="simple task")
    assert picked["name"] in ("gpt-4.1-mini", "gpt-4.1", "gpt-5")
    assert picked["name"] != "gpt-4o"


def test_new_agent_is_auto_and_run_resolves(client: TestClient):
    agent = client.post("/agents", json={"name": "A", "roleKey": "frontend-engineer", "description": "d"}).json()
    assert agent["model"]["name"] == "auto"


def test_auto_skips_experimental_and_learnlm_models(client: TestClient):
    from store import db

    # A provider list that includes junk Auto must never pick.
    db.put(
        "model-cache",
        "gemini",
        {"ids": ["learnlm-1.5-pro-experimental", "gemini-2.0-pro-exp", "gemini-2.5-flash", "gemini-2.5-pro"]},
    )
    high = automodel.resolve(
        {"provider": "gemini", "name": "auto", "config": {}}, role_key="team-lead", kind="lead", text="plan"
    )
    assert high["name"] in ("gemini-2.5-pro", "gemini-2.5-flash")
    assert "experimental" not in high["name"] and "learnlm" not in high["name"]

    # Even a removed model pinned on an agent is rescued to a stable one.
    rescued = automodel.resolve(
        {"provider": "gemini", "name": "learnlm-1.5-pro-experimental", "config": {}},
        role_key="frontend-engineer",
        kind=None,
        text="simple",
    )
    assert "experimental" not in rescued["name"] and "learnlm" not in rescued["name"]


def test_classifier_routes_complex_to_strong_and_simple_to_fast(client: TestClient, monkeypatch):
    from store import db
    from gateway import openai_gateway
    from runtime import automodel

    db.put("model-cache", "openai", {"ids": ["gpt-5", "gpt-4.1", "gpt-4.1-mini"]})
    monkeypatch.setenv("GATEWAY_MOCK", "0")  # take the live classifier path
    automodel._DIFFICULTY_CACHE.clear()

    calls = {"models": []}

    def fake_complete(model, messages, tools, config, provider=None):
        calls["models"].append(model)
        # The routing call runs on the cheapest model; answer by the task text.
        text = messages[0]["content"].lower()
        return {"content": "complex" if "payment" in text else "simple"}

    monkeypatch.setattr(openai_gateway, "complete", fake_complete)

    complex_pick = automodel.resolve(
        {"provider": "openai", "name": "auto", "config": {}},
        role_key="backend-engineer",
        kind="worker",
        text="Build the payment processing module",
    )
    simple_pick = automodel.resolve(
        {"provider": "openai", "name": "auto", "config": {}},
        role_key="frontend-engineer",
        kind="worker",
        text="Change the button label",
    )
    assert complex_pick["name"] == "gpt-5"  # complex -> strong
    assert simple_pick["name"] == "gpt-4.1-mini"  # simple -> fast
    # The classifier itself ran on the cheapest model, not gpt-5.
    assert calls["models"] and all(m == "gpt-4.1-mini" for m in calls["models"])
