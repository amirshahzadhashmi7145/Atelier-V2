"""OpenHands worker behind WorkerRunner. Graph files are not imported here as the implementation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from gateway import keys, llm
from runtime import board
from runtime.openhands.client import FakeOpenHands, set_client_factory
from runtime.openhands.runner import OpenHandsWorkerRunner, engine_of
from runtime.supervisor.worker import LoopWorkerRunner, WorkerRunner, get_runner
from store import db

from test_engine import client, fresh  # noqa: F401
from test_s12_backend import _activate

SECRET = "sk" + "-openhandsTESTKEY9999"
ROOT = Path(__file__).resolve().parents[2]


def _agent(client: TestClient, engine: str = "openhands", **extra) -> dict:
    db.put("stack", "react", {"id": "react", "name": "React", "version": "19", "packageAllowList": ["react", "react-dom"], "enabledByDefault": True})
    zones = extra.pop("zones", ["src/**", "package.json"])
    body = {
        "name": "Worker",
        "roleKey": extra.pop("roleKey", "frontend-engineer"),
        "description": "Implements UI.",
        "model": {"provider": "openai", "name": "gpt-4.1-mini", "config": {}},
        "toolIds": extra.pop("toolIds", ["files", "shell", "build_test"]),
        "stackIds": extra.pop("stackIds", ["react"]),
        "zones": zones,
        "workerEngine": engine,
        "scope": extra.pop("scope", {"does": ["user interfaces"], "neverDoes": ["servers"], "zones": zones}),
    }
    body.update(extra)
    return _activate(client, body)


def _workspace(client: TestClient, agent: dict, files: dict[str, str] | None = None) -> tuple[dict, dict]:
    project = client.post("/projects", json={"name": "OH", "agentId": agent["id"]}).json()
    folder = Path(project["folderPath"])
    package = {
        "name": "app",
        "private": True,
        "scripts": {"build": "node -e \"process.exit(0)\"", "test": "node -e \"process.exit(0)\""},
        "dependencies": {"react": "19.0.0"},
    }
    (folder / "package.json").write_text(json.dumps(package, indent=2))
    src = folder / "src"
    src.mkdir(exist_ok=True)
    (src / "App.tsx").write_text("export default function App() { return <div>Hi</div> }\n")
    for rel, text in (files or {}).items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "init"], cwd=folder, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=folder, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"], cwd=folder, capture_output=True)
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": None,
        "text": "Add a heading on the home page",
        "assignedAgentId": agent["id"],
        "routedBy": "user",
        "status": "queued",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
        "acceptanceCriteria": ["the heading is visible"],
        "reworkCount": 0,
    }
    db.put("task", task["id"], task)
    return project, task


def _run(project: dict, task: dict, fake: FakeOpenHands, via_loop: bool = False) -> dict:
    set_client_factory(lambda: fake)
    runner = LoopWorkerRunner() if via_loop else OpenHandsWorkerRunner()
    return runner.run({"project_id": project["id"], "task_id": task["id"], "text": task["text"]})


def test_openhands_runner_implements_worker_runner():
    assert isinstance(OpenHandsWorkerRunner(), WorkerRunner)
    runner = get_runner()
    assert callable(runner.run)
    assert engine_of({"workerEngine": "openhands"}) == "openhands"
    assert engine_of({}) == "loop"


def test_task_input_includes_task_criteria_handoff_and_feedback(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    board.write_handoff({"agentId": agent["id"]}, task, {"description": "last pass", "filesChanged": ["src/App.tsx"], "criteria": [{"text": "the heading is visible", "evidence": "src"}]})
    board.write_feedback(task, None, "changes_requested", "Make the heading larger", [{"targetKind": "criterion", "target": "the heading is visible", "wrong": "small", "expected": "larger"}])
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hello</h1> }\n"})
    _run(project, task, fake)
    prompt = fake.last_spec.prompt if fake.last_spec else ""
    assert "Add a heading on the home page" in prompt
    assert "the heading is visible" in prompt
    assert "last pass" in prompt
    assert "Make the heading larger" in prompt


def test_zone_violation_rejects(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"secret.txt": "nope"})
    result = _run(project, task, fake)
    assert result["handoffId"] is None
    feedback = board.latest_feedback(db.get("task", task["id"]))
    assert feedback and "zones" in (feedback.get("notes") or "")


def test_off_list_package_rejects(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(packages={"left-pad": "1.0.0"}, files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake)
    assert result["handoffId"] is None
    notes = (board.latest_feedback(db.get("task", task["id"])) or {}).get("notes") or ""
    assert "allow-list" in notes
    assert "left-pad" in notes


def test_failing_build_rejects(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(break_build=True, files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake)
    assert result["handoffId"] is None
    notes = (board.latest_feedback(db.get("task", task["id"])) or {}).get("notes") or ""
    assert "build_test" in notes


def test_rejection_becomes_rework_with_automatic_feedback(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"outside.md": "x"})
    _run(project, task, fake)
    row = db.get("task", task["id"])
    assert int(row.get("reworkCount") or 0) >= 1
    feedback = board.latest_feedback(row)
    assert feedback["verdict"] == "changes_requested"
    assert "Automatic check" in (feedback.get("notes") or "")


def test_files_changed_come_from_the_diff(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(
        files={"src/App.tsx": "export default function App() { return <h1>Hello</h1> }\n"},
        summary="I changed README.md",
    )
    result = _run(project, task, fake)
    assert result["status"] == "completed"
    note = db.get("handoff", result["handoffId"])
    assert "src/App.tsx" in (note.get("filesChanged") or [])
    assert "README.md" not in (note.get("filesChanged") or [])
    assert note.get("commitSha")


def test_cost_recorded_per_run_agent_and_role(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"}, cost_usd=1.25)
    result = _run(project, task, fake)
    run = db.get("run", result["runId"])
    assert run["costUsd"] == 1.25
    spend = db.get("agent-spend", agent["id"])
    assert spend and spend["usd"] == 1.25
    role = db.get("role-spend", agent["roleKey"])
    assert role and role["usd"] == 1.25


def test_spend_cap_stops_a_run(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    client.put("/settings/runs", json={"maxSpendPerRunUsd": 0.5, "maxIterations": 60, "maxMinutes": 45, "loopDetection": True})
    fake = FakeOpenHands(cost_usd=9.99, files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake)
    assert result["status"] == "failed"
    assert result["handoffId"] is None
    run = db.get("run", result["runId"])
    assert run.get("terminalCause") == "budget"


def test_event_log_is_saved_and_linked(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"}, events=[{"type": "action", "action": "edit", "path": "src/App.tsx"}])
    result = _run(project, task, fake)
    detail = client.get(f"/projects/{project['id']}/tasks/{task['id']}")
    assert detail.status_code == 200, detail.text
    logs = detail.json().get("sessionLogs") or []
    assert logs
    assert logs[0]["runId"] == result["runId"]
    assert logs[0].get("url")
    arts = [item for item in db.listing("artifact") if item.get("runId") == result["runId"] and item.get("name") == "openhands.jsonl"]
    assert arts


def test_sandbox_cleanup_runs_even_after_errors(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(error="boom")
    result = _run(project, task, fake)
    assert result["status"] == "failed"
    assert fake.cleaned is True


def test_keys_never_appear_in_logs_sandbox_files_or_api(client: TestClient, monkeypatch):
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: SECRET)
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(
        files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"},
        events=[{"type": "note", "content": SECRET}],
        leak_key_in="event",
    )
    result = _run(project, task, fake)
    folder = Path(project["folderPath"])
    blob = ""
    for path in folder.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            blob += path.read_text(errors="ignore")
    run = db.get("run", result["runId"])
    artifacts = [item for item in db.listing("artifact") if item.get("runId") == result["runId"]]
    board_json = client.get(f"/projects/{project['id']}/tasks/{task['id']}").text
    run_json = json.dumps(run)
    art_text = "".join(item.get("text") or "" for item in artifacts)
    assert SECRET not in blob
    assert SECRET not in run_json
    assert SECRET not in art_text
    assert SECRET not in board_json
    assert SECRET not in json.dumps(fake.last_spec.prompt if fake.last_spec else {})


def test_switching_engine_per_agent(client: TestClient):
    loop_agent = _agent(client, engine="loop", name="Loop Worker")
    oh_agent = _agent(client, engine="openhands", name="OH Worker")
    assert loop_agent["workerEngine"] == "loop"
    assert oh_agent["workerEngine"] == "openhands"
    project, task = _workspace(client, oh_agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake, via_loop=True)
    assert result["status"] == "completed"
    assert fake.last_spec is not None
    patched = client.patch(f"/agents/{oh_agent['id']}", json={"workerEngine": "loop"})
    assert patched.status_code == 200
    assert patched.json()["workerEngine"] == "loop"


def test_mcp_servers_are_passed_through(client: TestClient):
    db.put(
        "tool",
        "docs-mcp",
        {
            "id": "docs-mcp",
            "kind": "mcp",
            "name": "docs-mcp",
            "description": "Docs",
            "schema": {},
            "permission": "read",
            "config": {"url": "http://127.0.0.1:9/mcp"},
            "source": "user",
            "enabled": True,
        },
    )
    agent = _agent(client, toolIds=["files", "shell", "build_test", "docs-mcp", "search_data", "load_skill"])
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    _run(project, task, fake)
    mcp = (fake.last_spec.mcp if fake.last_spec else {}) or {}
    servers = mcp.get("mcpServers") or {}
    assert "docs-mcp" in servers
    assert "search_data" not in servers
    assert "load_skill" not in servers


def test_openhands_questions_become_handoff_open_questions(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(
        files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"},
        questions=["Which heading copy should we use?"],
    )
    result = _run(project, task, fake)
    note = db.get("handoff", result["handoffId"])
    assert "Which heading copy should we use?" in (note.get("openQuestions") or [])


def test_origin_remote_is_the_github_url():
    script = ROOT / "scripts" / "ensure_origin.sh"
    assert script.is_file()
    subprocess.run(["bash", str(script)], cwd=ROOT, check=True)
    url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True).strip()
    assert url == "https://github.com/amirshahzadhashmi7145/Atelier-V2.git"


def test_real_openhands_frontend_task_reviewed_by_supervisor(client: TestClient):
    if os.environ.get("RUN_REAL_LLM_TESTS") != "1":
        import pytest

        pytest.skip("RUN_REAL_LLM_TESTS=1")
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker is required for the live OpenHands run")
    from test_s13_lead import lead_agent, wait_plan, wait_until
    from test_engine import wait_status

    worker = _agent(client)
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "RealOH", "agentId": worker["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": lead["id"]}).status_code == 200
    posted = client.post(f"/projects/{project['id']}/messages", json={"text": "add a hello heading to the home page"}).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=60)
    plan = wait_plan(client, project["id"])
    assert client.post(f"/projects/{project['id']}/plans/{plan['planId']}/approve").status_code == 200
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") == "completed", timeout=600)
    assert finished
    kids = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"] and not item.get("supersededBy")]
    assert kids
    assert all(board.last_handoff(item) for item in kids)
    assert any(item.get("engine") == "openhands" for item in db.listing("run") if item.get("kind") == "worker")
