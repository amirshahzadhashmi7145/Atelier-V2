import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime.tools import dispatch
from store import db

from test_engine import client, fresh, wait_status  # noqa: F401
from test_s12_backend import _activate, _done, backend_agent, frontend_agent


def lead_agent(client: TestClient) -> dict:
    return _activate(
        client,
        {
            "name": "Team Lead",
            "roleKey": "team-lead",
            "toolIds": ["files", "shell", "build_test", "headless_browser"],
            "zones": [],
            "capabilities": {"stacks": [], "skills": ["definition-of-done"], "tags": ["supervisor"]},
            "scope": {
                "does": [
                    "splitting requests into tasks",
                    "assigning tasks",
                    "reviewing code against the task",
                    "deciding when work is done",
                ],
                "neverDoes": ["writing application code", "editing files"],
                "zones": [],
            },
        },
    )


def gate_plans(client: TestClient, on: bool = True) -> None:
    current = client.get("/settings/runs").json()
    current["approvePlansBeforeRunning"] = on
    assert client.put("/settings/runs", json=current).status_code == 200


def led_project(client: TestClient) -> tuple[dict, dict, dict, dict]:
    gate_plans(client)
    front = frontend_agent(client)
    back = backend_agent(client)
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "Led", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": back["id"]}).status_code == 200
    added = client.post(f"/projects/{project['id']}/members", json={"agentId": front["id"]})
    assert added.status_code == 200, added.text
    return added.json(), front, back, lead


def wait_until(predicate, timeout=20, interval=0.05):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    return last


def wait_plan(client: TestClient, project_id: str, timeout=20) -> dict:
    def find():
        rows = client.get(f"/projects/{project_id}/messages").json()
        return next((item for item in rows if item.get("label") == "plan" and item.get("planId")), None)

    plan = wait_until(find, timeout=timeout)
    assert plan, "plan was not shown before runs"
    return plan


def parent_of(project_id: str) -> dict | None:
    rows = [item for item in db.listing("task") if item.get("projectId") == project_id and not item.get("parentTaskId")]
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows[-1] if rows else None


def _one_child_plan(agent_id: str, text: str, criteria: list[str]) -> dict:
    return {
        "content": "Plan.",
        "tool_calls": [
            {
                "id": "c1",
                "name": "create_task",
                "arguments": {"text": text, "assignToAgentId": agent_id, "acceptanceCriteria": criteria, "order": 1},
            },
            {"id": "done", "name": "complete", "arguments": {"summary": {"description": "Plan ready."}}},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def test_team_lead_template_imports_with_scope_evals_and_supervisor_tag(client: TestClient):
    listed = client.get("/library", params={"kind": "agent"}).json()
    assert any(item["id"] == "team-lead" for item in listed)
    imported = client.post("/library/team-lead/import")
    assert imported.status_code == 201, imported.text
    agent = client.get(f"/agents/{imported.json()['id']}").json()
    assert agent["roleKey"] == "team-lead"
    assert agent["scope"]["does"] == [
        "splitting requests into tasks",
        "assigning tasks",
        "reviewing code against the task",
        "deciding when work is done",
    ]
    assert agent["scope"]["neverDoes"] == ["writing application code", "editing files"]
    assert agent["scope"]["zones"] == []
    assert agent["zones"] == []
    assert "supervisor" in (agent.get("capabilities") or {}).get("tags", [])
    assert {item["id"] for item in agent["evals"]} == {"eval_catch_bug", "eval_split", "eval_approve"}


def test_run_settings_default_approve_plans_and_review_cap(client: TestClient):
    from runtime.lead import spend_cap

    settings = client.get("/settings/runs").json()
    assert settings["approvePlansBeforeRunning"] is False
    assert settings["maxSpendPerReviewUsd"] == 1
    assert settings["maxSpendPerRunUsd"] == 5
    assert settings["maxSpendPerDayUsd"] == 0
    assert spend_cap(0, 0) is None
    assert spend_cap(None, 0) is None
    assert spend_cap(1, 0) == 1.0


def test_messages_route_to_the_lead(client: TestClient):
    project, front, back, lead = led_project(client)
    hello = client.post(f"/projects/{project['id']}/messages", json={"text": "hello"}).json()
    assert "runId" not in hello
    rows = client.get(f"/projects/{project['id']}/messages").json()
    agent_rows = [item for item in rows if item["role"] == "agent"]
    assert agent_rows[-1]["agentId"] == lead["id"]

    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    assert posted.get("runId")
    run = db.get("run", posted["runId"])
    assert run["agentId"] == lead["id"]
    assert run["kind"] == "lead"
    assert run["agentId"] != front["id"]
    assert run["agentId"] != back["id"]
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)


def test_plan_is_shown_before_any_child_run(client: TestClient):
    project, _front, _back, lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    assert wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)["status"] == "completed"
    plan = wait_plan(client, project["id"])
    assert "1." in plan["text"] and "2." in plan["text"]
    items = plan["planItems"]
    assert len(items) == 2
    assert items[0]["order"] == 1
    names = [item["agentName"] for item in items]
    assert names[0] == "Backend Engineer"
    assert names[1] == "Frontend Engineer"
    runs = [item for item in db.listing("run") if item.get("projectId") == project["id"]]
    assert len(runs) == 1
    assert runs[0]["kind"] == "lead"
    assert runs[0]["agentId"] == lead["id"]
    children = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"]]
    assert all(item["status"] == "planned" for item in children)
    parent = db.get("task", posted["taskId"])
    assert parent["status"] == "waiting_plan"


def test_second_plan_approve_does_not_resume_the_graph(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    resumes: list[object] = []
    monkeypatch.setattr("runtime.supervisor.graph.resume_supervisor", lambda *args, **kwargs: resumes.append(args))
    project, _front, _back, _lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    assert len(resumes) == 1
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    assert len(resumes) == 1
    rows = client.get(f"/projects/{project['id']}/messages").json()
    plan_msg = next(item for item in rows if item.get("planId") == plan["planId"])
    assert plan_msg.get("verdict") == "approve"


def test_approve_plan_advances_and_parent_completes_after_all_approvals(client: TestClient):
    project, _front, _back, lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    approved = client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve")
    assert approved.status_code == 200, approved.text
    finished = wait_until(
        lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed",
        timeout=30,
    )
    assert finished, "parent task did not complete after approvals"
    children = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"]]
    live = [item for item in children if not item.get("supersededBy")]
    assert live
    assert all(item.get("reviewStatus") == "approved" for item in live)
    rows = client.get(f"/projects/{project['id']}/messages").json()
    reviews = [item for item in rows if item.get("label") == "review" and item.get("verdict") == "approve"]
    assert reviews
    assert all(item["agentId"] == lead["id"] for item in reviews)
    wrap = [item for item in rows if item["role"] == "agent" and "What I checked" in (item.get("text") or "")]
    assert wrap
    project = client.get(f"/projects/{project['id']}").json()
    assert project.get("previewUrl")


def test_changes_requested_reruns_author_at_most_twice(client: TestClient):
    project, _front, back, _lead = led_project(client)
    openai_gateway.SCRIPTS.append(
        _one_child_plan(back["id"], "Implement notes. The mocked result omits delete.", ["notes can be deleted"])
    )
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build notes with delete"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    note = wait_until(
        lambda: next(
            (
                item
                for item in client.get(f"/projects/{project['id']}/messages").json()
                if "requested changes twice" in (item.get("text") or "")
            ),
            None,
        ),
        timeout=30,
    )
    assert note
    children = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"]]
    authors = [item for item in children if item.get("assignedAgentId") == back["id"]]
    assert len(authors) == 3
    reviews = [item for item in client.get(f"/projects/{project['id']}/messages").json() if item.get("verdict") == "changes_requested"]
    assert reviews
    parent = db.get("task", posted["taskId"])
    assert parent["status"] != "completed"


def test_seeded_bug_eval_requests_changes(client: TestClient):
    project, _front, back, _lead = led_project(client)
    openai_gateway.SCRIPTS.append(
        _one_child_plan(back["id"], "Implement notes. The mocked result omits delete.", ["notes can be deleted"])
    )
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "add a notes list with delete"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=40)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    review = wait_until(
        lambda: next(
            (
                item
                for item in client.get(f"/projects/{project['id']}/messages").json()
                if item.get("label") == "review" and item.get("verdict") == "changes_requested"
            ),
            None,
        ),
        timeout=90,
    )
    assert review
    assert "delete" in (review.get("text") or "").lower()
    wait_until(
        lambda: any("requested changes twice" in (item.get("text") or "") for item in client.get(f"/projects/{project['id']}/messages").json()),
        timeout=20,
    )


def test_lead_cannot_write_files(client: TestClient):
    project, _front, _back, lead = led_project(client)
    folder = Path(project["folderPath"])
    folder.mkdir(parents=True, exist_ok=True)
    refused = dispatch(
        {"id": "lead_write", "agentId": lead["id"], "kind": "lead", "projectId": project["id"], "folder": str(folder)},
        "files",
        {"op": "write", "path": "src/app.ts", "content": "nope"},
        lambda: False,
    )
    assert refused.get("refused") is True
    assert "cannot write" in refused["reason"]
    shell = dispatch(
        {"id": "lead_shell", "agentId": lead["id"], "kind": "lead", "projectId": project["id"], "folder": str(folder)},
        "shell",
        {"command": "ls"},
        lambda: False,
    )
    assert shell.get("refused") is True


def test_review_spend_cap_is_reported_not_retried(client: TestClient):
    settings = client.get("/settings/runs").json()
    settings["maxSpendPerReviewUsd"] = 1
    assert client.put("/settings/runs", json=settings).status_code == 200
    project, _front, back, _lead = led_project(client)
    openai_gateway.SCRIPTS.append(_one_child_plan(back["id"], "Ship the health endpoint", ["health returns ok"]))
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "add health"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=40)
    plan = wait_plan(client, project["id"])
    openai_gateway.SCRIPTS.append(_done([{"method": "GET", "path": "/health", "request": "", "response": "{ ok: true }"}]))
    openai_gateway.SCRIPTS.append({"content": "reviewing", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600_000}})
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    failed = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("run")
                if item.get("projectId") == project["id"] and item.get("kind") == "review" and item.get("status") == "failed"
            ),
            None,
        ),
        timeout=60,
    )
    assert failed
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert any("review exceeded its spend cap" in (item.get("text") or "").lower() for item in rows)
    reviews = [item for item in db.listing("run") if item.get("projectId") == project["id"] and item.get("kind") == "review"]
    assert len(reviews) == 1
    parent = db.get("task", posted["taskId"])
    assert parent["status"] != "completed"


def test_edit_plan_before_approve(client: TestClient):
    project, front, _back, _lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    items = list(plan["planItems"])
    items[1] = {**items[1], "text": "Build a smaller login form only", "assignedAgentId": front["id"]}
    edited = client.post(f"/projects/{project['id']}/plans/{plan['planId']}/edit", json={"items": items})
    assert edited.status_code == 200, edited.text
    task = db.get("task", items[1]["taskId"])
    assert task["text"] == "Build a smaller login form only"


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="set RUN_REAL_LLM_TESTS=1")
def test_real_todo_app_with_team_lead(client: TestClient):
    project, _front, _back, lead = led_project(client)
    os.environ.pop("GATEWAY_MOCK", None)
    posted = client.post(
        f"/projects/{project['id']}/messages",
        json={"text": "build a todo app with login"},
    ).json()
    deadline = time.time() + 900
    plan = None
    while time.time() < deadline and plan is None:
        rows = client.get(f"/projects/{project['id']}/messages").json()
        plan = next((item for item in rows if item.get("planId")), None)
        time.sleep(2)
    assert plan, "lead did not publish a plan"
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    while time.time() < deadline:
        parent = db.get("task", posted["taskId"])
        if parent and parent.get("status") == "completed":
            break
        time.sleep(2)
    parent = db.get("task", posted["taskId"])
    assert parent["status"] == "completed"
    children = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"] and not item.get("supersededBy")]
    assert children
    assert all(item.get("reviewStatus") == "approved" for item in children)
    project = client.get(f"/projects/{project['id']}").json()
    assert project.get("previewUrl")
    assert lead["id"]
