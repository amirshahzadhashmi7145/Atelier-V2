"""Fixes from the first live /contact test: OpenHands workers and supervisor behaviour."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from runtime import board, lead as leadlib, tools
from runtime.openhands.runner import OpenHandsWorkerRunner, engine_of
from runtime.supervisor.nodes import wait
from runtime.supervisor.state import empty_state
from runtime.supervisor.worker import LoopWorkerRunner, get_runner, set_runner
from runtime.tool_names import HANDLERS, offered_name, openai_tool_defs, resolve_offered, unmapped_offered
from store import db

from test_engine import client, fresh, ready, wait_status  # noqa: F401
from test_s12_backend import frontend_agent
from test_s13_lead import lead_agent, led_project, wait_plan
from test_s20_platform import qa_agent


def test_offered_names_round_trip_including_dots():
    names = {"repo.search", "repo.read", "create_task", "record_review"}
    for name in names:
        offered = offered_name(name)
        assert re.fullmatch(r"[A-Za-z0-9_-]+", offered)
        assert resolve_offered(offered, names) == name
    assert offered_name("repo.search") == "repo_search"


def test_offered_tools_map_to_handlers_including_mcp_ids(client: TestClient):
    db.put(
        "tool",
        "tool_8843",
        {
            "id": "tool_8843",
            "kind": "mcp",
            "name": "repo.search",
            "description": "Search the repo.",
            "schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            "permission": "read",
            "config": {},
            "source": "user",
            "enabled": True,
        },
    )
    db.put(
        "tool",
        "tool_8844",
        {
            "id": "tool_8844",
            "kind": "mcp",
            "name": "repo.read",
            "description": "Read a file.",
            "schema": {"type": "object", "properties": {"path": {"type": "string"}}},
            "permission": "read",
            "config": {},
            "source": "user",
            "enabled": True,
        },
    )
    lead = lead_agent(client)
    lead["toolIds"] = ["search_data", "tool_8843", "tool_8844"]
    db.put("agent", lead["id"], lead)
    offered = [item["function"]["name"] for item in openai_tool_defs(lead)]
    assert "tool_8843" not in offered
    assert "tool_8844" not in offered
    assert "repo.search" not in offered
    assert "repo_search" not in offered
    assert unmapped_offered(lead) == []
    for item in openai_tool_defs(lead):
        name = item["function"]["name"]
        resolved = resolve_offered(name, tools.allowed(lead))
        assert resolved in HANDLERS


def test_unmapped_tool_blocks_run_at_start(client: TestClient, monkeypatch):
    monkeypatch.setattr(tools, "unmapped_offered", lambda agent: ["ghost_tool"])
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Block", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "build a landing page with a hero"}).json()
    finished = wait_status(client, message["runId"], {"completed", "failed"}, timeout=12)
    assert finished["status"] == "failed"
    events = db.events_for(message["runId"])
    assert any("no handler" in str((item.get("payload") or {}).get("text") or "") for item in events)


def test_live_get_runner_is_openhands():
    set_runner(None)
    try:
        assert isinstance(get_runner(), OpenHandsWorkerRunner)
        assert engine_of({}) == "openhands"
        assert engine_of({"roleKey": "frontend-engineer"}) == "openhands"
    finally:
        set_runner(LoopWorkerRunner())


def test_review_input_contains_diff_and_build(client: TestClient):
    child = {
        "id": "task_rev",
        "text": "Add /contact",
        "assignedAgentId": "agt_fe",
        "acceptanceCriteria": ["heading Contact us"],
        "summary": "Added the page",
    }
    author = {
        "id": "run_author",
        "summary": {"description": "Added the page"},
        "gitDiff": "diff --git a/src/Contact.tsx b/src/Contact.tsx\n+export function Contact()",
        "buildTest": {"ok": True, "output": "build_test passed"},
    }
    packet = leadlib.review_packet(child, author)
    assert "# Git diff" in packet
    assert "src/Contact.tsx" in packet
    assert "# build_test" in packet
    assert "build_test passed" in packet


def test_approve_without_evidence_is_rejected(client: TestClient):
    lead = lead_agent(client)
    front = frontend_agent(client)
    project = client.post("/projects", json={"name": "Evidence", "agentId": lead["id"]}).json()
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "text": "Add /contact",
        "assignedAgentId": front["id"],
        "acceptanceCriteria": ["heading Contact us", "form with Name"],
        "status": "waiting_review",
    }
    db.put("task", task["id"], task)
    board.write_handoff({"agentId": front["id"]}, task, {"description": "done", "filesChanged": ["src/Contact.tsx"], "criteria": []})
    run = {"id": "run_rev", "agentId": lead["id"], "projectId": project["id"], "reviewOfTaskId": task["id"], "taskId": task["id"]}
    refused = tools.dispatch(run, "record_review", {"verdict": "approve", "notes": "looks good"}, lambda: False)
    assert refused.get("refused") is True
    assert "evidence" in (refused.get("reason") or "")


def test_one_user_request_produces_one_plan_and_no_duplicate_tasks(client: TestClient):
    project, front, _back, lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    wait_plan(client, project["id"])
    plans = [item for item in client.get(f"/projects/{project['id']}/messages").json() if item.get("label") == "plan"]
    assert len(plans) == 1
    parent = {"id": db.nid("task"), "projectId": project["id"], "text": "parent", "status": "running"}
    db.put("task", parent["id"], parent)
    run = {"id": "run_dup", "agentId": lead["id"], "projectId": project["id"], "taskId": parent["id"]}
    criteria = ["heading Contact us"]
    first = tools.dispatch(
        run,
        "create_task",
        {"text": "Add a /contact page", "assignToAgentId": front["id"], "acceptanceCriteria": criteria, "order": 1},
        lambda: False,
    )
    second = tools.dispatch(
        run,
        "create_task",
        {"text": "Add a /contact page again", "assignToAgentId": front["id"], "acceptanceCriteria": criteria, "order": 2},
        lambda: False,
    )
    assert first.get("taskId")
    assert second.get("taskId") == first.get("taskId")
    kids = [item for item in db.listing("task") if item.get("parentTaskId") == parent["id"] and not item.get("supersededBy")]
    assert len(kids) == 1


def test_supervisors_are_never_task_owners(client: TestClient):
    lead = lead_agent(client)
    qa = qa_agent(client)
    project = client.post("/projects", json={"name": "Owners", "agentId": lead["id"]}).json()
    parent = {"id": db.nid("task"), "projectId": project["id"], "text": "parent", "status": "running"}
    db.put("task", parent["id"], parent)
    run = {"id": "run_lead", "agentId": lead["id"], "projectId": project["id"], "taskId": parent["id"]}
    refused = tools.dispatch(
        run,
        "create_task",
        {"text": "QA the page", "assignToAgentId": qa["id"], "acceptanceCriteria": ["works"], "order": 1},
        lambda: False,
    )
    assert refused.get("refused") is True
    lead_refused = tools.dispatch(
        run,
        "create_task",
        {"text": "Plan more", "assignToAgentId": lead["id"], "acceptanceCriteria": ["plan"], "order": 2},
        lambda: False,
    )
    assert lead_refused.get("refused") is True


def test_supervisors_do_not_ask_anyone_to_proceed(client: TestClient):
    project, _front, _back, _lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    wait_plan(client, project["id"])
    rows = client.get(f"/projects/{project['id']}/messages").json()
    agent_text = " ".join((item.get("text") or "").lower() for item in rows if item.get("role") == "agent")
    assert "please proceed" not in agent_text
    assert "please execute" not in agent_text
    labels = {item.get("label") for item in rows if item.get("role") == "agent"}
    assert "plan" in labels


def test_failed_child_work_fails_the_parent(client: TestClient):
    lead = lead_agent(client)
    front = frontend_agent(client)
    project = client.post("/projects", json={"name": "FailParent", "agentId": lead["id"]}).json()
    parent = {"id": db.nid("task"), "projectId": project["id"], "text": "parent", "status": "running"}
    child = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": parent["id"],
        "assignedAgentId": front["id"],
        "text": "Add /contact",
        "status": "failed",
        "acceptanceCriteria": ["heading"],
    }
    db.put("task", parent["id"], parent)
    db.put("task", child["id"], child)
    leadlib.finish_parent(parent)
    assert (db.get("task", parent["id"]) or {}).get("status") == "failed"


def test_two_no_progress_failures_escalate(client: TestClient):
    lead = lead_agent(client)
    front = frontend_agent(client)
    project = client.post("/projects", json={"name": "Loop", "agentId": lead["id"]}).json()
    parent = {"id": db.nid("task"), "projectId": project["id"], "text": "parent", "status": "running"}
    child = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": parent["id"],
        "assignedAgentId": front["id"],
        "text": "Add /contact",
        "status": "queued",
        "acceptanceCriteria": ["heading"],
    }
    db.put("task", parent["id"], parent)
    db.put("task", child["id"], child)

    class FailRunner:
        def run(self, task_input: dict) -> dict:
            run = {
                "id": db.nid("run"),
                "projectId": project["id"],
                "taskId": task_input["task_id"],
                "status": "failed",
                "terminalCause": "loop",
                "kind": "worker",
            }
            db.put("run", run["id"], run)
            db.append_event(run["id"], "RUN_FAILED", {"text": "no progress", "cause": "loop"})
            return {"taskId": task_input["task_id"], "runId": run["id"], "handoffId": None, "status": "failed"}

    set_runner(FailRunner())
    try:
        state = empty_state(
            project_id=project["id"],
            parent_task_id=parent["id"],
            supervisor_agent_id=lead["id"],
            lead_run_id="run_lead",
            current_layer=1,
        )
        state["current_task_id"] = child["id"]
        first = wait(state)
        assert first.get("escalate_to_user") is not True
        second = wait({**state, **first, "current_task_id": child["id"]})
        assert second.get("escalate_to_user") is True
        needs = [item for item in db.listing("need") if item.get("projectId") == project["id"]]
        assert any("no progress twice" in (item.get("question") or "") for item in needs)
    finally:
        set_runner(LoopWorkerRunner())
