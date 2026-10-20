import ast
import json
from pathlib import Path

from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime import board
from runtime.supervisor.graph import compiled, thread_config
from store import db

from test_engine import client, fresh, wait_status  # noqa: F401
from test_s12_backend import _activate
from test_s13_lead import _one_child_plan, gate_plans, lead_agent, led_project, wait_plan, wait_until
from test_s15_roles_board import _worker

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "api" / "runtime" / "supervisor"
FORBIDDEN_MODULES = {
    "openai",
    "google.genai",
    "google.generativeai",
    "anthropic",
    "litellm",
    "langchain_openai",
    "langchain_google_genai",
    "langchain_anthropic",
    "langchain_community.chat_models",
    "langchain.chat_models",
    "langchain_core.language_models",
}
FORBIDDEN_NAMES = {"ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI", "AzureChatOpenAI"}


def _graph_state(parent_id: str) -> dict:
    snap = compiled().get_state(thread_config(parent_id))
    return dict(snap.values or {})


def test_happy_path_plan_dispatch_handoff_approve_wrap_up(client: TestClient):
    project, _front, _back, lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    assert wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)["status"] == "completed"
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=30)
    assert finished
    kids = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"] and not item.get("supersededBy")]
    assert kids and all(item.get("reviewStatus") == "approved" for item in kids)
    assert all(board.last_handoff(item) for item in kids)
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert any("What I checked" in (item.get("text") or "") for item in rows)
    viewed = client.get(f"/projects/{project['id']}").json()
    assert viewed.get("previewUrl")
    steps = {item["step"] for item in viewed.get("supervisorSteps") or []}
    assert "done" in steps
    assert lead["id"]


def test_changes_requested_loops_back_with_task_handoff_and_feedback(client: TestClient):
    project, _front, back, _lead = led_project(client)
    openai_gateway.SCRIPTS.append(
        _one_child_plan(back["id"], "Implement notes. The mocked result omits delete.", ["notes can be deleted"])
    )
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build notes with delete"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    retry = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("task")
                if item.get("parentTaskId") == posted["taskId"] and item.get("previousTaskId")
            ),
            None,
        ),
        timeout=20,
    )
    assert retry
    assert retry["assignedAgentId"] == back["id"]
    packet = board.rework_packet(retry)
    assert "Implement notes" in packet
    assert "Last handoff" in packet
    assert "Latest feedback" in packet
    wait_until(
        lambda: any("requested changes twice" in (item.get("text") or "") for item in client.get(f"/projects/{project['id']}/messages").json()),
        timeout=30,
    )


def test_two_reworks_then_next_layer_then_user(client: TestClient):
    assert client.post(
        "/roles",
        json={"id": "release-gate", "name": "Release Gate", "kind": "supervisor", "reportsTo": None, "layer": 2, "zones": [], "tags": ["supervisor"]},
    ).status_code == 201
    assert client.patch("/roles/team-lead", json={"reportsTo": "release-gate"}).status_code == 200
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    lead = lead_agent(client)
    gate = _activate(
        client,
        {
            "name": "Release Gate",
            "roleKey": "release-gate",
            "toolIds": ["files", "shell", "build_test"],
            "zones": [],
            "capabilities": {"stacks": [], "skills": [], "tags": ["supervisor"]},
            "scope": {"does": ["reviewing releases"], "neverDoes": ["writing application code"], "zones": []},
        },
    )
    project = client.post("/projects", json={"name": "Escalate", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": worker["id"]}).status_code == 200
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": gate["id"]}).status_code == 200
    openai_gateway.SCRIPTS.append(_one_child_plan(worker["id"], "Implement notes. The mocked result omits delete.", ["notes can be deleted"]))
    gate_plans(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build notes with delete"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    gate_review = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("run")
                if item.get("projectId") == project["id"] and item.get("kind") == "review" and item.get("agentId") == gate["id"]
            ),
            None,
        ),
        timeout=30,
    )
    assert gate_review
    user_note = wait_until(
        lambda: next(
            (
                item
                for item in client.get(f"/projects/{project['id']}/messages").json()
                if "requested changes twice" in (item.get("text") or "")
            ),
            None,
        ),
        timeout=45,
    )
    assert user_note
    parent = db.get("task", posted["taskId"])
    assert parent["status"] != "completed"


def test_new_supervisor_role_as_data_runs_on_same_graph(client: TestClient):
    assert client.post(
        "/roles",
        json={"id": "desk-lead", "name": "Desk Lead", "kind": "supervisor", "reportsTo": None, "layer": 1, "zones": [], "tags": ["supervisor", "planning"]},
    ).status_code == 201
    desk = _activate(
        client,
        {
            "name": "Desk Lead",
            "roleKey": "desk-lead",
            "toolIds": ["files", "shell", "build_test"],
            "zones": [],
            "capabilities": {"stacks": [], "skills": ["definition-of-done"], "tags": ["supervisor"]},
            "scope": {
                "does": ["splitting requests into tasks", "reviewing code against the task"],
                "neverDoes": ["writing application code"],
                "zones": [],
            },
        },
    )
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    project = client.post("/projects", json={"name": "Desk", "agentId": desk["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": worker["id"]}).status_code == 200
    openai_gateway.SCRIPTS.append(_one_child_plan(worker["id"], "Build the React UI against the contract", ["criteria met"]))
    gate_plans(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a small page"}).json()
    run = db.get("run", posted["runId"])
    assert run["kind"] == "lead"
    assert run["agentId"] == desk["id"]
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=30)
    assert finished
    reviews = [item for item in db.listing("run") if item.get("projectId") == project["id"] and item.get("kind") == "review"]
    assert reviews and all(item["agentId"] == desk["id"] for item in reviews)


def test_approved_task_walks_reports_to_chain(client: TestClient):
    assert client.post(
        "/roles",
        json={"id": "release-gate", "name": "Release Gate", "kind": "supervisor", "reportsTo": None, "layer": 2, "zones": [], "tags": ["supervisor"]},
    ).status_code == 201
    assert client.patch("/roles/team-lead", json={"reportsTo": "release-gate"}).status_code == 200
    project, front, _back, lead = led_project(client)
    gate = _activate(
        client,
        {
            "name": "Release Gate",
            "roleKey": "release-gate",
            "toolIds": ["files", "shell", "build_test"],
            "zones": [],
            "capabilities": {"stacks": [], "skills": [], "tags": ["supervisor"]},
            "scope": {"does": ["reviewing releases"], "neverDoes": ["writing application code"], "zones": []},
        },
    )
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": gate["id"]}).status_code == 200
    openai_gateway.SCRIPTS.append(_one_child_plan(front["id"], "Build the React UI against the contract", ["criteria met"]))
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a small page"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    gate_review = wait_until(
        lambda: next(
            (
                item
                for item in db.listing("run")
                if item.get("projectId") == project["id"] and item.get("kind") == "review" and item.get("agentId") == gate["id"]
            ),
            None,
        ),
        timeout=30,
    )
    assert gate_review
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=30)
    assert finished
    assert lead["id"]


def test_run_resumes_from_checkpoint_after_simulated_restart(client: TestClient):
    project, _front, _back, _lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    from runtime.supervisor.graph import reset_compiled

    reset_compiled()
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=30)
    assert finished
    values = _graph_state(posted["taskId"])
    assert values.get("task_ids")


def test_graph_state_holds_ids_not_copied_records(client: TestClient):
    project, _front, _back, _lead = led_project(client)
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "build a todo app with login"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=20)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=30)
    values = _graph_state(posted["taskId"])
    assert values["task_ids"]
    assert all(isinstance(item, str) for item in values["task_ids"])
    assert all(isinstance(item, str) for item in values.get("decision_ids") or [])
    assert all(isinstance(item, str) for item in values.get("handoff_ids") or [])
    blob = json.dumps(values)
    assert "acceptanceCriteria" not in blob
    assert "filesChanged" not in blob
    assert "Last handoff" not in blob
    assert "Latest feedback" not in blob
    for step in (values.get("status_by_task") or {}).values():
        assert step in {"planning", "working", "reviewing", "escalated", "done"}


def test_graph_code_does_not_import_provider_or_langchain_chat():
    found = []
    extra = [
        ROOT / "api" / "runtime" / "fit.py",
        ROOT / "api" / "runtime" / "lessons.py",
        ROOT / "api" / "runtime" / "needs.py",
    ]
    for path in [*sorted(GRAPH_DIR.glob("*.py")), *extra]:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_MODULES or alias.name.split(".")[0] in FORBIDDEN_MODULES:
                        found.append(f"{path.name}:{node.lineno}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module in FORBIDDEN_MODULES or any(
                    node.module == item or node.module.startswith(item + ".") for item in FORBIDDEN_MODULES
                ):
                    found.append(f"{path.name}:{node.lineno}:from {node.module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_NAMES:
                        found.append(f"{path.name}:{node.lineno}:{alias.name}")
    assert found == []
