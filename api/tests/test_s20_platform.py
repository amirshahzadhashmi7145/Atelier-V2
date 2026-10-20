from fastapi.testclient import TestClient

from gateway import openai_gateway
from gateway.exceptions import ProviderError
from runtime import board, fit, lessons, needs
from runtime.mcp import handler
from store import db

from test_engine import client, fresh, ready, wait_status  # noqa: F401
from test_s12_backend import _activate, _done, frontend_agent
from test_s13_lead import _one_child_plan, gate_plans, lead_agent, wait_plan, wait_until
from test_s15_roles_board import _worker


def qa_agent(client: TestClient) -> dict:
    return _activate(
        client,
        {
            "name": "QA Engineer",
            "roleKey": "qa-engineer",
            "toolIds": ["files", "shell", "build_test", "headless_browser"],
            "zones": [],
            "capabilities": {"stacks": [], "skills": ["definition-of-done"], "tags": ["supervisor"]},
            "scope": {
                "does": ["testing against stated acceptance criteria", "running the build and preview", "recording review verdicts with evidence"],
                "neverDoes": ["writing application code", "editing files", "inventing requirements that are not in the criteria"],
                "zones": [],
            },
        },
    )


def test_existing_empty_reports_to_picks_up_the_seed_parent(client: TestClient):
    from runtime import roles as rolelib

    lead = db.get("role", "team-lead")
    db.put("role", "team-lead", {**lead, "reportsTo": None})
    db.delete("meta", "seed-parent-link")
    rolelib.sync_roles()
    assert db.get("role", "team-lead")["reportsTo"] == "qa-engineer"
    db.put("role", "team-lead", {**db.get("role", "team-lead"), "reportsTo": None})
    rolelib.sync_roles()
    assert db.get("role", "team-lead")["reportsTo"] is None


def test_qa_is_a_seed_supervisor_on_the_same_graph(client: TestClient):
    rows = client.get("/roles").json()
    qa = next(item for item in rows if item["id"] == "qa-engineer")
    lead = next(item for item in rows if item["id"] == "team-lead")
    assert qa["kind"] == "supervisor"
    assert qa["layer"] == 2
    assert lead["reportsTo"] == "qa-engineer"
    listed = client.get("/library", params={"kind": "agent"}).json()
    assert any(item["id"] == "qa-engineer" for item in listed)


def _qa_project(client: TestClient) -> tuple[dict, dict, dict, dict]:
    gate_plans(client)
    front = frontend_agent(client)
    lead = lead_agent(client)
    qa = qa_agent(client)
    project = client.post("/projects", json={"name": "QA", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": front["id"]}).status_code == 200
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": qa["id"]}).status_code == 200
    return project, front, lead, qa


def test_qa_reviews_only_after_team_lead_approved(client: TestClient):
    project, front, lead, qa = _qa_project(client)
    openai_gateway.SCRIPTS.append(_one_child_plan(front["id"], "Build the React UI against the contract", ["criteria met"]))
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a small page"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=30)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    qa_review = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("run")
                if item.get("projectId") == project["id"] and item.get("kind") == "review" and item.get("agentId") == qa["id"]
            ),
            None,
        ),
        timeout=60,
    )
    assert qa_review
    lead_reviews = [
        item
        for item in db.listing("run")
        if item.get("projectId") == project["id"] and item.get("kind") == "review" and item.get("agentId") == lead["id"]
    ]
    assert lead_reviews
    assert min(item["startedAt"] for item in lead_reviews) <= qa_review["startedAt"]
    kids = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"] and not item.get("supersededBy")]
    assert kids
    assert any(item.get("reviewStatus") == "approved" or board.latest_feedback(item) for item in kids)


def test_qa_feedback_returns_to_the_original_worker(client: TestClient, monkeypatch):
    from gateway import mock_turns

    reviews = {"n": 0}

    def scripted(blob: str):
        reviews["n"] += 1
        if reviews["n"] == 1:
            notes = "All criteria are met."
            verdict = "approve"
        else:
            notes = "always run tests before complete"
            verdict = "changes_requested"
        return [
            {
                "content": notes,
                "tool_calls": [{"id": "rev", "name": "record_review", "arguments": {"verdict": verdict, "notes": notes}}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ]

    monkeypatch.setattr(mock_turns, "_review_turns", scripted)
    project, front, _lead, _qa = _qa_project(client)
    openai_gateway.SCRIPTS.append(_one_child_plan(front["id"], "Build the React UI against the contract", ["criteria met"]))
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a small page"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=30)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    retry = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("task")
                if item.get("parentTaskId") == posted["taskId"]
                and item.get("assignedAgentId") == front["id"]
                and (item.get("previousTaskId") or int(item.get("reworkCount") or 0) >= 1)
            ),
            None,
        ),
        timeout=70,
    )
    assert retry
    assert retry["assignedAgentId"] == front["id"]


def test_suggestion_picks_highest_first_try_then_cheaper_within_ten_points(client: TestClient):
    cheap = {"provider": "openai", "name": "gpt-4.1-mini"}
    dear = {"provider": "openai", "name": "gpt-5"}
    for index in range(10):
        fit.record("frontend-engineer", dear, first_try=index < 8, reworks=0 if index < 8 else 1, cost=0.40, live=True)
        fit.record("frontend-engineer", cheap, first_try=index < 8, reworks=0 if index < 8 else 1, cost=0.12, live=True)
    pick = fit.suggestion("frontend-engineer")
    assert pick["name"] == "gpt-4.1-mini"
    assert "8 of 10" in pick["reason"]
    winner = {"provider": "openai", "name": "gpt-4.1"}
    other = {"provider": "openai", "name": "gpt-4o-mini"}
    for index in range(10):
        fit.record("backend-engineer", winner, first_try=index < 9, reworks=0, cost=0.30, live=True)
        fit.record("backend-engineer", other, first_try=index < 5, reworks=0, cost=0.05, live=True)
    assert fit.suggestion("backend-engineer")["name"] == "gpt-4.1"
    thin = {"provider": "openai", "name": "o3"}
    for _ in range(4):
        fit.record("team-lead", thin, first_try=True, reworks=0, cost=0.01, live=True)
    assert fit.suggestion("team-lead") is None
    overlay = fit.overlay("o3", "team-lead")
    assert overlay["reason"] == "not enough data yet"
    assert overlay["suggested"] is False


def test_new_agents_default_to_suggestion_existing_never_switch(client: TestClient):
    model = {"provider": "openai", "name": "gpt-4.1-mini"}
    for _ in range(5):
        fit.record("frontend-engineer", model, first_try=True, reworks=0, cost=0.12, live=True)
    created = client.post("/agents", json={"name": "Fresh", "roleKey": "frontend-engineer", "description": "UI"}).json()
    assert created["model"]["name"] == "gpt-4.1-mini"
    kept = client.post(
        "/agents",
        json={
            "name": "Kept",
            "roleKey": "frontend-engineer",
            "description": "UI",
            "model": {"provider": "openai", "name": "gpt-4o", "config": {}},
        },
    ).json()
    other = {"provider": "openai", "name": "gpt-5"}
    for _ in range(8):
        fit.record("frontend-engineer", other, first_try=True, reworks=0, cost=0.01, live=True)
    again = client.get(f"/agents/{kept['id']}").json()
    assert again["model"]["name"] == "gpt-4o"


def test_plan_approval_defaults_off_and_needs_you_is_escalation_only(client: TestClient):
    settings = client.get("/settings/runs").json()
    assert settings["approvePlansBeforeRunning"] is False
    front = frontend_agent(client)
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "Auto", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": front["id"]}).status_code == 200
    openai_gateway.SCRIPTS.append(_one_child_plan(front["id"], "Build the React UI against the contract", ["criteria met"]))
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a small page"}).json()
    worker = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("run")
                if item.get("projectId") == project["id"]
                and item.get("id") != posted["runId"]
                and item.get("kind") not in ("lead", "review")
            ),
            None,
        ),
        timeout=30,
    )
    assert worker
    assert client.get(f"/projects/{project['id']}/needs").json() == []
    needs.write(project["id"], posted["taskId"], "escalate", "Retry or stop?", posted["runId"])
    needs.write(project["id"], posted["taskId"], "budget", "Spend cap hit.", posted["runId"])
    needs.write(project["id"], posted["taskId"], "question", "Which auth provider?", posted["runId"])
    rows = client.get(f"/projects/{project['id']}/needs").json()
    assert {item["kind"] for item in rows} == {"escalate", "budget", "question"}
    assert all(item["question"] for item in rows)


def test_user_answer_writes_to_the_board_and_resumes(client: TestClient):
    questions = {"id": "q", "name": "raise_clarification", "arguments": {"questions": ["Which auth?"]}}
    openai_gateway.SCRIPTS.append({"tool_calls": [questions], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    agent_id = ready(client)
    run = client.post("/runs", json={"agentId": agent_id, "workspace": {"kind": "scaffold", "template": "local"}, "task": "Ask"}).json()
    wait_status(client, run["id"], {"waiting_user"})
    project = client.post("/projects", json={"name": "Ask", "agentId": agent_id}).json()
    task = {"id": "task_ask", "projectId": project["id"], "assignedAgentId": agent_id, "text": "Ask", "status": "running"}
    db.put("task", task["id"], task)
    live = db.get("run", run["id"])
    live["projectId"] = project["id"]
    live["taskId"] = task["id"]
    db.put("run", run["id"], live)
    row = needs.write(project["id"], task["id"], "question", "Which auth?", run["id"])
    answered = client.post(f"/needs/{row['id']}/answer", json={"text": "use email"})
    assert answered.status_code == 200, answered.text
    finished = wait_status(client, run["id"], {"completed", "failed"})
    assert finished["status"] == "completed"
    detail = client.get(f"/projects/{project['id']}/tasks/{task['id']}").json()
    assert any((item.get("summary") or "") == "use email" for item in detail.get("events") or [])


def test_backup_model_used_only_on_provider_failure(client: TestClient, monkeypatch):
    from gateway import llm

    calls = []
    orig = llm._provider_stream

    def fake(provider, model, messages, tools, config, stream, tool_choice):
        calls.append(model)
        if model == "gpt-4o":
            raise ProviderError("429 rate limit")
        yield from orig(provider, model, messages, tools, config, stream, tool_choice)

    monkeypatch.setattr(llm, "_provider_stream", fake)
    agent = _activate(
        client,
        {
            "name": "With backup",
            "roleKey": "frontend-engineer",
            "toolIds": ["files"],
            "zones": ["."],
            "model": {"provider": "openai", "name": "gpt-4o", "config": {}},
            "backupModel": {"provider": "openai", "name": "gpt-4.1-mini", "config": {}},
            "scope": {"does": ["ui"], "neverDoes": [], "zones": ["."]},
        },
    )
    openai_gateway.SCRIPTS.append(_done())
    run = client.post("/runs", json={"agentId": agent["id"], "workspace": {"kind": "scaffold", "template": "local"}, "task": "Ship"}).json()
    finished = wait_status(client, run["id"], {"completed", "failed"})
    assert finished["status"] == "completed"
    assert finished.get("backupUsed") is True
    assert (finished.get("actualModel") or {}).get("name") == "gpt-4.1-mini"
    assert "gpt-4o" in calls and "gpt-4.1-mini" in calls
    assert int(finished.get("backupUseCount") or 0) >= 1

    calls.clear()

    def bad_answer(provider, model, messages, tools, config, stream, tool_choice):
        calls.append(model)
        yield from orig(provider, model, messages, tools, config, stream, tool_choice)

    monkeypatch.setattr(llm, "_provider_stream", bad_answer)
    openai_gateway.SCRIPTS.append(_done())
    second = client.post("/runs", json={"agentId": agent["id"], "workspace": {"kind": "scaffold", "template": "local"}, "task": "Again"}).json()
    done = wait_status(client, second["id"], {"completed", "failed"})
    assert done["status"] == "completed"
    assert done.get("backupUsed") is not True
    assert calls and all(name == "gpt-4o" for name in calls)


def test_lessons_after_rework_then_approval_capped_merged_and_deletable(client: TestClient):
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    task = {
        "id": "task_lesson",
        "assignedAgentId": worker["id"],
        "reworkCount": 1,
        "text": "Build the page",
    }
    db.put("task", task["id"], task)
    none = lessons.maybe_write({**task, "reworkCount": 0}, {"notes": "always run tests before complete"})
    assert none is None
    first = lessons.maybe_write(task, {"notes": "always run tests before complete"})
    assert first and first["text"] == "always run tests before complete"
    packet = lessons.for_prompt("frontend-engineer")
    assert "always run tests before complete" in packet
    listed = client.get("/roles/frontend-engineer/lessons").json()
    assert listed and listed[0]["text"] == "always run tests before complete"
    lessons.maybe_write(task, {"notes": "always run tests before complete and stay inside the zone"})
    rows = lessons.for_role("frontend-engineer")
    assert len(rows) == 1
    client.put("/settings/runs", json={**client.get("/settings/runs").json(), "maxLessonsPerRole": 1})
    lessons.maybe_write(task, {"notes": "never skip the build"})
    assert len(lessons.for_role("frontend-engineer")) == 1
    run = {
        "id": "run_lesson",
        "agentId": worker["id"],
        "status": "running",
    }
    db.put("run", run["id"], run)
    taught = handler.invoke(run, "get_lessons", {})
    assert "never skip" in (taught.get("output") or "") or "always run tests" in (taught.get("output") or "")
    lesson_id = lessons.for_role("frontend-engineer")[0]["id"]
    assert client.delete(f"/roles/frontend-engineer/lessons/{lesson_id}").status_code == 204
    assert client.get("/roles/frontend-engineer/lessons").json() == []


def test_qa_cannot_write_files(client: TestClient):
    from pathlib import Path

    from runtime.tools import dispatch

    qa = qa_agent(client)
    project = client.post("/projects", json={"name": "QAWrite", "agentId": qa["id"]}).json()
    folder = Path(project["folderPath"])
    folder.mkdir(parents=True, exist_ok=True)
    refused = dispatch(
        {"id": "qa_write", "agentId": qa["id"], "kind": "review", "projectId": project["id"], "folder": str(folder)},
        "files",
        {"op": "write", "path": "index.html", "content": "x"},
        lambda: False,
    )
    assert refused.get("refused") is True
    assert "cannot write" in refused["reason"]
