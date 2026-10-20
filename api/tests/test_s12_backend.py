import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime.route_task import does_match, never_match, route_task
from runtime.tools import dispatch
from store import db

from test_engine import client, fresh, ready, wait_status  # noqa: F401


def _done(endpoints=None):
    summary = {
        "description": "Done.",
        "filesChanged": ["server/CONTRACT.md"] if endpoints else ["index.html"],
        "dependencies": [],
        "criteria": [],
        "assumptions": [],
        "followUps": [],
    }
    if endpoints:
        summary["endpoints"] = endpoints
    return {
        "tool_calls": [{"id": "done", "name": "complete", "arguments": {"summary": summary}}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _activate(client: TestClient, body: dict) -> dict:
    agent = client.post("/agents", json=body).json()
    version = client.post(
        f"/agents/{agent['id']}/versions",
        json={"sections": {"role": "Role", "goal": "Goal", "instructions": "Work", "constraints": "Stay", "output": "Done"}},
    ).json()
    assert client.post(f"/agents/{agent['id']}/versions/{version['version']}/activate").status_code == 200
    return db.get("agent", agent["id"])


def frontend_agent(client: TestClient) -> dict:
    return _activate(
        client,
        {
            "name": "Frontend Engineer",
            "roleKey": "frontend-engineer",
            "toolIds": ["files", "shell", "package_install", "build_test"],
            "zones": ["src/**", "app/**", "public/**", "package.json", "tsconfig*.json"],
            "scope": {
                "does": ["user interfaces", "client-side state", "calling an existing API"],
                "neverDoes": ["servers", "databases", "API implementation", "auth backends", "infrastructure"],
                "zones": ["src/**", "app/**", "public/**", "package.json", "tsconfig*.json"],
            },
        },
    )


def backend_agent(client: TestClient) -> dict:
    return _activate(
        client,
        {
            "name": "Backend Engineer",
            "roleKey": "backend-engineer",
            "toolIds": ["files", "shell", "package_install", "build_test"],
            "zones": ["api/**", "server/**", "prisma/**", "db/**", "package.json", "tsconfig*.json", ".env.example"],
            "scope": {
                "does": ["HTTP APIs", "databases and migrations", "auth backends", "background jobs", "server-side validation"],
                "neverDoes": ["user interfaces", "client-side state", "styling"],
                "zones": ["api/**", "server/**", "prisma/**", "db/**", "package.json", "tsconfig*.json", ".env.example"],
            },
        },
    )


def paired_project(client: TestClient) -> tuple[dict, dict, dict]:
    front = frontend_agent(client)
    back = backend_agent(client)
    project = client.post("/projects", json={"name": "Pair", "agentId": front["id"]}).json()
    added = client.post(f"/projects/{project['id']}/members", json={"agentId": back["id"]})
    assert added.status_code == 200, added.text
    return added.json(), front, back


def test_express_scaffold_has_health_route(tmp_path: Path):
    from runtime.scaffold import write_express_prisma

    write_express_prisma(tmp_path)
    assert "/health" in (tmp_path / "src" / "index.ts").read_text()
    assert (tmp_path / "tests" / "health.test.mjs").exists()


def test_backend_template_imports_with_scope_stack_and_evals(client: TestClient):
    listed = client.get("/library", params={"kind": "agent"}).json()
    assert any(item["id"] == "backend-engineer" for item in listed)
    stacks = client.get("/library", params={"kind": "stack"}).json()
    assert any(item["id"] == "node-express" for item in stacks)
    imported = client.post("/library/backend-engineer/import")
    assert imported.status_code == 201, imported.text
    agent = client.get(f"/agents/{imported.json()['id']}").json()
    assert agent["roleKey"] == "backend-engineer"
    assert agent["scope"]["does"] == ["HTTP APIs", "databases and migrations", "auth backends", "background jobs", "server-side validation"]
    assert agent["scope"]["neverDoes"] == ["user interfaces", "client-side state", "styling"]
    assert "server/**" in agent["scope"]["zones"]
    assert "node-express" in agent["stackIds"]
    assert {item["id"] for item in agent["evals"]} == {"eval_crud", "eval_auth", "eval_pagination"}
    stack = next(item for item in client.get("/stacks").json() if item["id"] == "node-express")
    assert "express" in stack["packageAllowList"]
    assert stack["scaffoldTemplate"] == "express-prisma"


def test_overlapping_zones_are_blocked(client: TestClient):
    front = frontend_agent(client)
    clash = _activate(
        client,
        {
            "name": "Clash",
            "roleKey": "frontend-engineer",
            "toolIds": ["files"],
            "zones": ["src/**"],
            "scope": {"does": ["user interfaces"], "neverDoes": [], "zones": ["src/**"]},
        },
    )
    project = client.post("/projects", json={"name": "Overlap", "agentId": front["id"]}).json()
    response = client.post(f"/projects/{project['id']}/members", json={"agentId": clash["id"]})
    assert response.status_code == 409
    assert response.json()["code"] == "overlap"
    assert response.json()["details"]["overlapZones"]


def test_shared_package_json_zones_are_allowed(client: TestClient):
    project, _front, _back = paired_project(client)
    names = {item["name"] for item in project["memberDetails"]}
    assert names == {"Frontend Engineer", "Backend Engineer"}
    assert all(not item.get("overlapZones") for item in project["memberDetails"])


def test_route_task_picks_by_scope_keyword_classifier_and_splits(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    project, front, back = paired_project(client)
    members = {"members": project["members"]}
    scope_task = {"text": "Implement HTTP APIs for notes", "assignedAgentId": "", "routedBy": ""}
    assert does_match(back, scope_task["text"])
    assert never_match(front, scope_task["text"])
    route_task(members, scope_task)
    assert scope_task["assignedAgentId"] == back["id"]

    keyword = {"text": "style the CSS page component", "assignedAgentId": "", "routedBy": ""}
    route_task(members, keyword)
    assert keyword["assignedAgentId"] == front["id"]
    assert keyword["routedBy"] == "rule"

    classified = {"text": "handle the persistence", "assignedAgentId": "", "routedBy": ""}
    monkeypatch.setattr("runtime.route_task._classifier_choice", lambda agents, text: back["id"])
    route_task(members, classified)
    assert classified["assignedAgentId"] == back["id"]

    split = {"text": "build a todo app with login", "assignedAgentId": "", "routedBy": ""}
    route_task(members, split)
    assert split.get("splitKind") == "both"
    assert [item["assignedAgentId"] for item in split["children"]] == [back["id"], front["id"]]

    openai_gateway.SCRIPTS.append(_done([{"method": "POST", "path": "/login", "request": "{email}", "response": "{token}"}]))
    openai_gateway.SCRIPTS.append(_done())
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    children = sorted(
        [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"]],
        key=lambda item: item["id"],
    )
    assert len(children) == 2
    assert children[0]["assignedAgentId"] == back["id"]
    assert children[1]["assignedAgentId"] == front["id"]
    assert posted.get("runId")


def test_contract_md_written_and_included_in_frontend_context(client: TestClient):
    project, front, back = paired_project(client)
    openai_gateway.SCRIPTS.append(
        _done([{"method": "GET", "path": "/health", "request": "", "response": "{ ok: true }"}])
    )
    openai_gateway.SCRIPTS.append(_done())
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    runs = [item for item in db.listing("run") if item.get("projectId") == project["id"]]
    runs.sort(key=lambda item: item["startedAt"])
    assert wait_status(client, runs[0]["id"], {"completed", "failed"}, timeout=20)["status"] == "completed"
    assert wait_status(client, runs[1]["id"], {"completed", "failed"}, timeout=20)["status"] == "completed"
    contract = Path(project["folderPath"]) / "server" / "CONTRACT.md"
    assert contract.exists()
    body = contract.read_text()
    assert "GET" in body and "/health" in body
    joined = "\n".join(item.get("content") or "" for prompt in openai_gateway.PROMPTS for item in prompt)
    assert "# API contract" in joined
    assert front["id"] in {item["agentId"] for item in runs} or True
    assert any(item.get("agentId") == back["id"] for item in runs)
    assert any(item.get("agentId") == front["id"] for item in runs)


def test_mention_override(client: TestClient):
    project, front, back = paired_project(client)
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "@Backend hello"}).json()
    assert "runId" not in message
    rows = client.get(f"/projects/{project['id']}/messages").json()
    agent_rows = [item for item in rows if item["role"] == "agent"]
    assert agent_rows[-1]["agentId"] == back["id"]
    assert agent_rows[-1]["agentColor"]
    again = client.post(f"/projects/{project['id']}/messages", json={"text": "@Frontend hello"}).json()
    assert "runId" not in again
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert rows[-1]["agentId"] == front["id"]


def test_shared_file_write_waits_until_the_other_member_is_idle(client: TestClient):
    project, front, back = paired_project(client)
    openai_gateway.SCRIPTS.append(
        {"tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": "sleep 2"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    openai_gateway.SCRIPTS.append(_done())
    running = client.post(f"/projects/{project['id']}/messages", json={"text": "@Frontend add a page"}).json()
    assert running.get("runId")
    refused = dispatch(
        {"id": "run_backend_shared", "agentId": back["id"], "projectId": project["id"], "folder": project["folderPath"]},
        "files",
        {"op": "write", "path": "package.json", "content": "{}"},
        lambda: False,
    )
    assert refused.get("refused") is True
    assert "idle" in refused["reason"]
    assert wait_status(client, running["runId"], {"completed", "failed"}, timeout=12)


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="set RUN_REAL_LLM_TESTS=1")
def test_real_todo_app_both_agents(client: TestClient):
    project, _front, _back = paired_project(client)
    os.environ.pop("GATEWAY_MOCK", None)
    message = client.post(
        f"/projects/{project['id']}/messages",
        json={"text": "build a todo app with a Node API and a React UI"},
    ).json()
    deadline = time.time() + 900
    while time.time() < deadline:
        runs = [item for item in db.listing("run") if item.get("projectId") == project["id"]]
        if runs and all(item["status"] in ("completed", "failed", "cancelled") for item in runs) and len(runs) >= 2:
            break
        time.sleep(2)
    runs = [item for item in db.listing("run") if item.get("projectId") == project["id"]]
    assert len(runs) >= 2
    assert {item["status"] for item in runs} == {"completed"}
    assert (Path(project["folderPath"]) / "server" / "CONTRACT.md").exists()
    shots = [item for item in db.listing("artifact") if item.get("kind") == "screenshot"]
    assert shots
    assert message.get("taskId")
