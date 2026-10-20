from fastapi.testclient import TestClient

from app import models_catalog
from gateway import llm
from runtime import compile as compiler
from runtime import roles as rolelib
from store import db

from test_engine import client, fresh, ready  # noqa: F401


def test_seed_role_is_editable_and_reset(client: TestClient):
    patched = client.patch(
        "/roles/backend-engineer",
        json={"name": "API Worker", "layer": 3, "zones": ["server/**"], "tags": ["custom"], "colour": "#111111"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["name"] == "API Worker"
    assert body["kind"] == "worker"
    assert body["id"] == "backend-engineer"
    locked = client.patch("/roles/backend-engineer", json={"kind": "supervisor", "id": "other"})
    assert locked.status_code == 200
    assert locked.json()["kind"] == "worker"
    assert locked.json()["id"] == "backend-engineer"
    reset = client.post("/roles/backend-engineer/reset")
    assert reset.status_code == 200
    assert reset.json()["name"] == "Backend Engineer"
    assert reset.json()["layer"] == 0
    assert reset.json()["zones"] == ["server/**"]
    assert reset.json()["contractFile"] == "server/CONTRACT.md"


def test_contract_file_outside_zones_is_rejected(client: TestClient):
    failed = client.patch(
        "/roles/backend-engineer",
        json={"zones": ["server/**"], "contractFile": "api/CONTRACT.md"},
    )
    assert failed.status_code == 422
    assert "zones" in failed.json()["message"].lower()
    ok = client.patch(
        "/roles/backend-engineer",
        json={"zones": ["server/**"], "contractFile": "server/CONTRACT.md"},
    )
    assert ok.status_code == 200


def test_backend_seed_migration_sets_server_contract(client: TestClient):
    db.put(
        "role",
        "backend-engineer",
        {
            "id": "backend-engineer",
            "name": "Backend Engineer",
            "kind": "worker",
            "reportsTo": "team-lead",
            "layer": 0,
            "zones": ["api/**", "server/**"],
            "tags": ["backend"],
            "colour": "#d97706",
            "contractFile": "api/CONTRACT.md",
        },
    )
    db.delete("meta", "backend-contract-server")
    rolelib.sync_roles()
    row = db.get("role", "backend-engineer")
    assert row["zones"] == ["server/**"]
    assert row["contractFile"] == "server/CONTRACT.md"
    listed = client.get("/roles").json()
    back = next(item for item in listed if item["id"] == "backend-engineer")
    assert back["contractFile"] == "server/CONTRACT.md"


def test_supervisor_compiled_prompt_has_no_worker_lines(client: TestClient):
    created = client.post(
        "/agents",
        json={
            "name": "Lead",
            "roleKey": "team-lead",
            "description": "Plans",
            "model": {"provider": "openai", "name": "gpt-4.1-mini", "config": {}},
            "toolIds": ["create_task", "record_review"],
            "zones": [],
            "scope": {"does": ["planning"], "neverDoes": ["writing application code"], "zones": []},
            "capabilities": {"stacks": [], "skills": [], "tags": ["supervisor"]},
        },
    )
    assert created.status_code == 201
    preview = client.post(
        f"/agents/{created.json()['id']}/compile-preview",
        json={
            "sections": {
                "role": "Lead",
                "goal": "Done",
                "instructions": "Split work",
                "constraints": "No files",
                "output": "Review",
            },
            "toolIds": ["create_task", "record_review"],
            "skillIds": [],
            "stackIds": [],
            "scope": {"does": ["planning"], "neverDoes": ["writing application code"], "zones": []},
        },
    )
    assert preview.status_code == 200
    text = preview.json()["compiled"]
    assert "Prefer files.edit" not in text
    assert "build_test before complete" not in text
    assert "create_task:" in text
    assert "record_review:" in text
    assert "files:" not in text
    worker = compiler.compile_prompt(
        {"role": "Dev", "goal": "G", "instructions": "Work", "constraints": "C", "output": "O"},
        ["files"],
        [],
        [],
        worker=True,
    )["compiled"]
    assert "Prefer files.edit" in worker


def test_model_filter_hides_non_chat_and_retired(client: TestClient, monkeypatch):
    assert models_catalog.is_chat("gpt-4.1")
    assert models_catalog.is_chat("gemini-2.5-flash")
    assert not models_catalog.is_chat("models/gemini-2.0-flash-preview-image-generation")
    assert not models_catalog.is_chat("gemini-2.5-computer-use-preview-10-2025")
    assert not models_catalog.is_chat("gpt-4o-realtime-preview")
    assert not models_catalog.is_chat("text-embedding-3-small")
    assert not models_catalog.is_chat("sora-2")
    assert models_catalog.is_retired("gpt-4o-retired")
    monkeypatch.setattr(models_catalog, "_shutdown_date", lambda name: "2020-01-01" if "old-chat" in name else None)
    assert models_catalog.is_retired("old-chat", today="2026-10-20")
    db.put(
        "model-cache",
        "openai",
        {
            "ids": [
                "gpt-4.1",
                "gpt-4o-realtime-preview",
                "text-embedding-3-small",
                "gpt-4o-retired",
            ]
        },
    )
    db.put(
        "model-cache",
        "gemini",
        {
            "ids": [
                "gemini-2.5-flash",
                "models/gemini-2.0-flash-preview-image-generation",
                "gemini-2.5-computer-use-preview-10-2025",
            ]
        },
    )
    names = {item["name"] for item in client.get("/models").json()}
    assert "gpt-4.1" in names
    assert "gemini-2.5-flash" in names
    assert "gpt-4o-realtime-preview" not in names
    assert "text-embedding-3-small" not in names
    assert "gpt-4o-retired" not in names
    assert "models/gemini-2.0-flash-preview-image-generation" not in names
    assert "gemini-2.5-computer-use-preview-10-2025" not in names


def test_agent_without_provider_key_is_blocked(client: TestClient, monkeypatch):
    monkeypatch.setenv("GATEWAY_MOCK", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    agent_id = ready(client)
    blocked = client.post(
        "/runs",
        json={"agentId": agent_id, "workspace": {"kind": "scaffold", "template": "local"}, "task": "Build"},
    )
    assert blocked.status_code == 422
    assert "API key" in blocked.json()["message"]
    assert blocked.json()["code"] == "key_missing"
    assert llm.missing_key_message(db.get("agent", agent_id))
