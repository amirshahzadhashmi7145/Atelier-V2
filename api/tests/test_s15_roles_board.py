import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime import board, lead as leadlib, roles as rolelib
from runtime.route_task import route_task
from store import db

from test_engine import client, fresh, wait_status  # noqa: F401
from test_s12_backend import _activate
from test_s13_lead import _one_child_plan, lead_agent, wait_plan, wait_until

ROOT = Path(__file__).resolve().parents[2]
LOGIC = [
    ROOT / "api" / "runtime" / "route_task.py",
    ROOT / "api" / "runtime" / "lead.py",
    ROOT / "api" / "runtime" / "loop.py",
    ROOT / "api" / "runtime" / "members.py",
    *sorted((ROOT / "api" / "runtime" / "supervisor").glob("*.py")),
    *sorted((ROOT / "api" / "runtime" / "openhands").glob("*.py")),
]
FORBIDDEN = re.compile(r"\b(frontend|backend|team[ -]lead|qa)\b", re.I)


def test_role_name_literals_are_absent_from_logic():
    found = []
    for path in LOGIC:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and FORBIDDEN.search(node.value):
                found.append(f"{path.name}:{node.lineno}:{node.value}")
    assert found == []


def test_seed_roles_exist(client: TestClient):
    rows = client.get("/roles").json()
    ids = {item["id"] for item in rows}
    assert {"frontend-engineer", "backend-engineer", "team-lead"} <= ids
    lead = next(item for item in rows if item["id"] == "team-lead")
    assert lead["kind"] == "supervisor"
    back = next(item for item in rows if item["id"] == "backend-engineer")
    assert back["contractFile"] == "api/CONTRACT.md"
    assert client.get("/tags").json()["tags"]


def _worker(
    client: TestClient,
    role_id: str,
    name: str,
    does: list[str],
    never: list[str],
    tags: list[str] | None = None,
    zones: list[str] | None = None,
) -> dict:
    area = zones or ["src/**"]
    return _activate(
        client,
        {
            "name": name,
            "roleKey": role_id,
            "toolIds": ["files", "shell", "build_test"],
            "zones": area,
            "capabilities": {"stacks": [], "skills": [], "tags": tags or []},
            "scope": {"does": does, "neverDoes": never, "zones": area},
        },
    )


def test_new_worker_role_as_data_is_routed(client: TestClient):
    created = client.post(
        "/roles",
        json={
            "id": "mobile-engineer",
            "name": "Mobile Engineer",
            "kind": "worker",
            "reportsTo": "team-lead",
            "layer": 0,
            "zones": ["ios/**"],
            "tags": ["mobile"],
            "colour": "#0f766e",
        },
    )
    assert created.status_code == 201, created.text
    mobile = _worker(
        client,
        "mobile-engineer",
        "Mobile Engineer",
        ["mobile apps"],
        ["servers"],
        ["mobile"],
        zones=["ios/**"],
    )
    other = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], ["servers"], zones=["src/**"])
    project = client.post("/projects", json={"name": "Phone", "agentId": other["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": mobile["id"]}).status_code == 200
    project = client.get(f"/projects/{project['id']}").json()
    task = {"text": "build the mobile checkout flow", "assignedAgentId": "", "routedBy": ""}
    route_task(project, task)
    assert task["assignedAgentId"] == mobile["id"]


def test_new_supervisor_in_the_chain_receives_approved_tasks(client: TestClient):
    qa_role = client.post(
        "/roles",
        json={"id": "release-gate", "name": "Release Gate", "kind": "supervisor", "reportsTo": None, "layer": 2, "zones": [], "tags": ["supervisor"]},
    )
    assert qa_role.status_code == 201, qa_role.text
    patched = client.patch("/roles/team-lead", json={"reportsTo": "release-gate", "layer": 1})
    assert patched.status_code == 200, patched.text
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
    project = client.post("/projects", json={"name": "Chain", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": worker["id"]}).status_code == 200
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": gate["id"]}).status_code == 200
    project = client.get(f"/projects/{project['id']}").json()
    chain = rolelib.supervisor_chain(worker)
    assert [item["id"] for item in chain] == ["team-lead", "release-gate"]
    first = rolelib.first_reviewer(project, worker)
    nxt = rolelib.next_reviewer(project, worker, first)
    assert first["id"] == lead["id"]
    assert nxt["id"] == gate["id"]


def test_complete_writes_handoff_and_review_writes_feedback(client: TestClient):
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "Board", "agentId": lead["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": worker["id"]}).status_code == 200
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": None,
        "text": "Ship a page",
        "assignedAgentId": worker["id"],
        "routedBy": "agent",
        "status": "running",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
        "acceptanceCriteria": ["The button is visible"],
        "reworkCount": 0,
        "createdAt": db.now(),
    }
    db.put("task", task["id"], task)
    run = {
        "id": db.nid("run"),
        "agentId": worker["id"],
        "taskId": task["id"],
        "projectId": project["id"],
        "task": task["text"],
        "status": "running",
    }
    summary = {
        "description": "Page shipped.",
        "filesChanged": ["index.html"],
        "criteria": [{"text": "The button is visible", "evidence": "screenshot"}],
        "followUps": ["hover state?"],
    }
    board.write_handoff(run, task, summary)
    notes = db.listing("handoff")
    assert any(item["taskId"] == task["id"] and item["summary"] == "Page shipped." for item in notes)
    review_run = {"id": db.nid("run"), "agentId": lead["id"], "reviewOfTaskId": task["id"], "taskId": task["id"], "projectId": project["id"]}
    result = leadlib.apply_review(
        review_run,
        "changes_requested",
        "Button contrast is low",
        [{"targetKind": "criterion", "target": "The button is visible", "wrong": "low contrast", "expected": "4.5:1"}],
    )
    assert result.get("done") is True
    feedback = [item for item in db.listing("review-feedback") if item["taskId"] == task["id"]]
    assert feedback and feedback[-1]["verdict"] == "changes_requested"
    assert feedback[-1]["items"][0]["expected"] == "4.5:1"


def test_rework_input_contains_task_handoff_and_feedback(client: TestClient):
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "Rework", "agentId": lead["id"]}).json()
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": None,
        "text": "Ship a page",
        "assignedAgentId": worker["id"],
        "status": "queued",
        "acceptanceCriteria": ["visible"],
        "reworkCount": 1,
        "createdAt": db.now(),
    }
    db.put("task", task["id"], task)
    board.write_handoff({"id": "r1", "agentId": worker["id"]}, task, {"description": "First pass", "filesChanged": ["a.ts"], "criteria": []})
    board.write_feedback(task, lead, "changes_requested", "Need a test", [{"targetKind": "file", "target": "a.ts", "wrong": "no test", "expected": "add a test"}])
    packet = board.rework_packet(task)
    assert "Ship a page" in packet
    assert "First pass" in packet
    assert "Need a test" in packet
    assert "Latest feedback" in packet


def test_max_two_reworks_then_next_supervisor_layer(client: TestClient):
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
    assert gate_review, "the next supervisor layer never received the task"


def test_task_detail_lists_handoff_and_feedback_in_order(client: TestClient):
    worker = _worker(client, "frontend-engineer", "Web Engineer", ["user interfaces"], [])
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "Detail", "agentId": lead["id"]}).json()
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": None,
        "text": "Ship a page",
        "assignedAgentId": worker["id"],
        "status": "completed",
        "acceptanceCriteria": ["visible"],
        "reworkCount": 0,
        "screenshotRefs": [],
        "summary": "done",
        "diffRef": None,
        "routedBy": "agent",
        "createdAt": db.now(),
    }
    db.put("task", task["id"], task)
    board.write_handoff({"id": "r1", "agentId": worker["id"]}, task, {"description": "First pass", "filesChanged": ["a.ts"]})
    board.write_feedback(task, lead, "changes_requested", "again")
    detail = client.get(f"/projects/{project['id']}/tasks/{task['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["task"]["id"] == task["id"]
    kinds = [item["kind"] for item in body["events"]]
    assert kinds == ["handoff", "feedback"]
