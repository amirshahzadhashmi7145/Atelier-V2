"""OpenHands worker behind WorkerRunner. Graph files are not imported here as the implementation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
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
    assert engine_of({}) == "openhands"
    from runtime.supervisor.worker import set_runner

    set_runner(None)
    assert isinstance(get_runner(), OpenHandsWorkerRunner)
    set_runner(LoopWorkerRunner())


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
    assert "running the tests and the production build" in prompt
    assert "a preview is served automatically" in prompt
    assert "development server in the background" not in prompt
    assert "Do not search the filesystem for skills" in prompt


def test_backend_packet_skips_browser_and_skill_hunt(client: TestClient):
    agent = _agent(client, roleKey="backend-engineer", zones=["server/**"], stackIds=[])
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"server/index.js": "module.exports = {}\n"})
    _run(project, task, fake)
    prompt = fake.last_spec.prompt if fake.last_spec else ""
    assert "Do not start a dev server" in prompt
    assert "development server in the background" not in prompt
    assert "Do not search the filesystem for skills" in prompt


def test_openhands_driver_registers_browser_toolset():
    text = (ROOT / "api" / "runtime" / "openhands" / "driver.py").read_text()
    assert "BrowserToolSet" in text
    assert "mount_dir=" not in text
    assert "volumes=" in text or "volumes=[" in text
    assert "stdout.flush" in text
    assert "_watch" in text
    assert "get_combined_metrics" in text
    assert '"type": "cost"' in text


def test_openhands_cost_events_update_spend():
    from runtime.openhands.client import _iter_jsonl

    recorded: list[float] = []
    _events, result = _iter_jsonl(
        [
            json.dumps({"type": "cost", "costUsd": 0.12}),
            json.dumps({"type": "action", "action": "edit", "path": "src/App.tsx"}),
            json.dumps({"type": "result", "costUsd": 0.15, "summary": "done"}),
        ],
        on_cost=recorded.append,
    )
    assert recorded == [0.12]
    assert result["costUsd"] == 0.15


def test_openhands_terminal_events_are_named_and_deduped(client: TestClient):
    from runtime.openhands.runner import _publish_oh_event

    db.put("run", "run_ev", {"id": "run_ev", "status": "running"})
    n = [0]
    run = db.get("run", "run_ev")
    _publish_oh_event(run, {"type": "TerminalAction", "command": "ls -la"}, n)
    _publish_oh_event(run, {"type": "TerminalAction", "command": "ls -la"}, n)
    _publish_oh_event(run, {"type": "CmdOutputObservation", "command": "ls -la", "content": "ok"}, n)
    events = db.events_for("run_ev")
    called = [item for item in events if item["type"] == "TOOL_CALLED"]
    assert len(called) == 1
    assert called[0]["payload"]["name"] == "terminal"
    assert called[0]["payload"]["arguments"]["command"] == "ls -la"
    assert any(item["type"] == "TOOL_RESULT" and item["payload"]["name"] == "terminal" for item in events)


def test_openhands_events_are_appended_while_running(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(
        files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"},
        events=[{"type": "action", "action": "edit", "path": "src/App.tsx"}, {"type": "message", "content": "Drew the board."}],
    )
    result = _run(project, task, fake)
    events = db.events_for(result["runId"])
    assert any(item["type"] == "TOOL_CALLED" and (item.get("payload") or {}).get("name") == "edit" for item in events)
    assert any(item["type"] == "MODEL_OUTPUT" and "board" in str((item.get("payload") or {}).get("text") or "") for item in events)


def test_openhands_does_not_start_a_second_worker_for_the_same_task(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    started = threading.Event()
    release = threading.Event()

    class SlowFake(FakeOpenHands):
        def run(self, spec):
            started.set()
            release.wait(5)
            return super().run(spec)

    fake = SlowFake(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    set_client_factory(lambda: fake)
    runner = OpenHandsWorkerRunner()
    payload = {"project_id": project["id"], "task_id": task["id"], "text": task["text"]}
    results: list[dict] = []

    def go() -> None:
        results.append(runner.run(payload))

    first = threading.Thread(target=go)
    second = threading.Thread(target=go)
    first.start()
    assert started.wait(5)
    second.start()
    release.set()
    first.join(timeout=10)
    second.join(timeout=10)
    workers = [item for item in db.listing("run") if item.get("taskId") == task["id"] and item.get("kind") == "worker"]
    assert len(workers) == 1
    assert len(results) == 2
    assert results[0]["runId"] == results[1]["runId"] == workers[0]["id"]


def test_reap_orphans_fails_stuck_running_workers(client: TestClient):
    from runtime import project_runs

    db.put(
        "run",
        "run_stuck",
        {"id": "run_stuck", "status": "running", "kind": "worker", "taskId": "task_stuck", "startedAt": db.now(), "costUsd": 0},
    )
    db.put("task", "task_stuck", {"id": "task_stuck", "status": "running", "text": "stuck"})
    db.put(
        "run",
        "run_wait",
        {"id": "run_wait", "status": "waiting_user", "kind": "lead", "taskId": "task_wait", "startedAt": db.now()},
    )
    assert project_runs.reap_orphans() >= 1
    assert db.get("run", "run_stuck")["status"] == "failed"
    assert db.get("task", "task_stuck")["status"] == "failed"
    assert db.get("run", "run_wait")["status"] == "waiting_user"


def test_supervisor_steps_stop_saying_working_after_orphan_reap(client: TestClient):
    from runtime import project_runs
    from runtime.supervisor import steps as steplib

    db.put(
        "run",
        "run_stuck2",
        {"id": "run_stuck2", "status": "running", "kind": "worker", "taskId": "task_stuck2", "projectId": "prj_stuck", "startedAt": db.now()},
    )
    db.put("task", "task_stuck2", {"id": "task_stuck2", "status": "running", "text": "stuck", "assignedAgentId": ""})
    db.put(
        "supervisor-run",
        "parent_stuck",
        {"id": "parent_stuck", "projectId": "prj_stuck", "steps": [{"taskId": "task_stuck2", "step": "working", "runId": "run_stuck2"}]},
    )
    project_runs.reap_orphans()
    rows = steplib.steps_for_project("prj_stuck")
    assert rows and rows[0]["step"] != "working"


def test_zone_violation_rejects(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"secret.txt": "nope"})
    result = _run(project, task, fake)
    assert result["handoffId"] is None
    feedback = board.latest_feedback(db.get("task", task["id"]))
    assert feedback and "zones" in (feedback.get("notes") or "")


def test_lockfile_is_not_a_zone_violation(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(
        files={
            "src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n",
            "package-lock.json": "{}",
        }
    )
    result = _run(project, task, fake)
    assert result["status"] == "completed"


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


def test_committed_openhands_files_still_count_as_changed(client: TestClient):
    from runtime.openhands import sandbox

    agent = _agent(client)
    project, task = _workspace(client, agent)
    work = sandbox.prepare(project, task)
    try:
        target = work.folder / "src" / "App.tsx"
        target.write_text("export default function App() { return <h1>Hi</h1> }\n")
        sandbox.git(work.folder, ["add", "-A"])
        sandbox.git(work.folder, ["commit", "-m", "agent"])
        assert "src/App.tsx" not in sandbox.changed_files(work.folder, project)
        assert "src/App.tsx" in sandbox.changed_files(work.folder, project, baseline=work.baseline)
    finally:
        work.cleanup()


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
    assert run.get("costSource") == "openhands"
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


def test_restore_host_access_skips_docker_when_readable(tmp_path, monkeypatch):
    from runtime.openhands import sandbox

    folder = tmp_path / "repo"
    folder.mkdir()
    (folder / "package.json").write_text("{}")
    called: list = []
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *args, **kwargs: called.append(args))
    sandbox.restore_host_access(folder)
    assert called == []


def test_openhands_sandbox_is_writable_for_container(client: TestClient):
    from runtime.openhands import sandbox

    agent = _agent(client)
    project, task = _workspace(client, agent)
    work = sandbox.prepare(project, task)
    try:
        assert work.folder.stat().st_mode & 0o222
        (work.folder / "conversations").mkdir()
        assert "conversations" not in sandbox.changed_files(work.folder, project)
    finally:
        work.cleanup()


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


def test_live_workers_always_use_openhands(client: TestClient):
    loop_agent = _agent(client, engine="loop", name="Loop Worker")
    oh_agent = _agent(client, engine="openhands", name="OH Worker")
    assert loop_agent["workerEngine"] == "openhands"
    assert oh_agent["workerEngine"] == "openhands"
    patched = client.patch(f"/agents/{oh_agent['id']}", json={"workerEngine": "loop"})
    assert patched.status_code == 200
    assert patched.json()["workerEngine"] == "openhands"
    from runtime.supervisor.worker import set_runner

    set_runner(None)
    project, task = _workspace(client, oh_agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    set_client_factory(lambda: fake)
    result = get_runner().run({"project_id": project["id"], "task_id": task["id"], "text": task["text"]})
    set_runner(LoopWorkerRunner())
    assert result["status"] == "completed"
    assert fake.last_spec is not None


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
    servers = (fake.last_spec.mcp if fake.last_spec else {}) or {}
    assert "docs-mcp" in servers
    assert "atelier" in servers
    assert "mcpServers" not in servers
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


def _studio_secrets() -> Path:
    return Path.home() / ".atelier-projects" / ".secrets"


def _settings_key_present() -> bool:
    studio = _studio_secrets() / "providers"
    return bool(studio.is_dir() and list(studio.glob("*.enc")))


def _hydrate_studio_secrets() -> bool:
    src = _studio_secrets()
    if not _settings_key_present():
        return False
    dest = Path(os.environ.get("PROJECTS_DIR") or "") / ".secrets"
    if not dest.parent.exists():
        return False
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest.joinpath("providers").is_dir() and bool(list(dest.joinpath("providers").glob("*.enc")))


def _gateway_price(events: list[dict], model: str) -> float:
    total = 0.0
    for item in events or []:
        usage = item.get("token_usage") or item.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        inp = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        if inp or out:
            total += llm.cost_usd(model, {"input_tokens": int(inp), "output_tokens": int(out)})
    return round(total, 6)


def test_real_openhands_frontend_task_reviewed_by_supervisor(client: TestClient):
    if os.environ.get("RUN_REAL_LLM_TESTS") != "1":
        import pytest

        pytest.skip("RUN_REAL_LLM_TESTS=1")
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker is required for the live OpenHands run")
    if not _settings_key_present():
        import pytest

        pytest.skip("no provider key in the Settings encrypted store")
    assert _hydrate_studio_secrets()
    from runtime.supervisor.worker import set_runner
    from test_s13_lead import gate_plans, lead_agent, wait_plan, wait_until
    from test_engine import wait_status

    set_runner(None)
    worker = _agent(client)
    lead = lead_agent(client)
    project = client.post("/projects", json={"name": "RealOH", "agentId": worker["id"]}).json()
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": lead["id"]}).status_code == 200
    gate_plans(client)
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
    oh_runs = [item for item in db.listing("run") if item.get("kind") == "worker" and item.get("engine") == "openhands"]
    for run in oh_runs:
        arts = [item for item in db.listing("artifact") if item.get("runId") == run["id"] and item.get("name") == "openhands.jsonl"]
        events: list[dict] = []
        for art in arts:
            for line in (art.get("text") or "").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        reported = float(run.get("costUsd") or 0)
        gateway = _gateway_price(events, (run.get("model") or {}).get("name") or "gpt-4.1-mini")
        db.put("cost-compare", run["id"], {"openhandsUsd": reported, "gatewayUsd": gateway, "gapUsd": round(reported - gateway, 6)})


def _live_model() -> dict:
    from gateway import openai_gateway

    spec = openai_gateway.default_model_spec()
    return {**spec, "config": spec.get("config") or {}}


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_real_contact_page_openhands_qa(client: TestClient, monkeypatch, attempt):
    if os.environ.get("RUN_REAL_LLM_TESTS") != "1":
        import pytest

        pytest.skip("RUN_REAL_LLM_TESTS=1")
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker is required for the live OpenHands run")
    from dotenv import load_dotenv
    from gateway import openai_gateway

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not _settings_key_present() and not openai_gateway.gemini_api_key() and not openai_gateway.openai_api_key():
        import pytest

        pytest.skip("no provider key in the Settings encrypted store or env")
    _hydrate_studio_secrets()
    monkeypatch.setenv("GATEWAY_MOCK", "0")
    from runtime.supervisor.worker import set_runner
    from test_s13_lead import gate_plans, lead_agent, wait_until
    from test_s20_platform import qa_agent
    from test_engine import wait_status

    set_runner(None)
    gate_plans(client, False)
    model = {"provider": "gemini", "name": os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash", "config": {}}
    if not openai_gateway.gemini_api_key():
        model = _live_model()
    from runtime.scaffold import write_vite_react_ts

    zones = [
        "src/**",
        "app/**",
        "public/**",
        "index.html",
        "vite.config.*",
        "package.json",
        "tsconfig*.json",
        "tailwind.config.*",
        "postcss.config.*",
    ]
    worker = _agent(client, model=model, zones=zones)
    db.put(
        "stack",
        "react",
        {
            "id": "react",
            "name": "React",
            "version": "19",
            "packageAllowList": [
                "react",
                "react-dom",
                "react-router-dom",
                "lucide-react",
                "@types/react",
                "@types/react-dom",
                "vite",
                "@vitejs/*",
                "typescript",
            ],
            "enabledByDefault": True,
        },
    )
    lead = lead_agent(client)
    lead["model"] = model
    db.put("agent", lead["id"], lead)
    qa = qa_agent(client)
    qa["model"] = model
    db.put("agent", qa["id"], qa)
    project = client.post("/projects", json={"name": f"Contact-{attempt}", "agentId": lead["id"]}).json()
    folder = Path(project["folderPath"])
    write_vite_react_ts(folder)
    subprocess.run(["git", "init"], cwd=folder, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=folder, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"], cwd=folder, capture_output=True)
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": worker["id"]}).status_code == 200
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": qa["id"]}).status_code == 200
    posted = client.post(
        f"/projects/{project['id']}/messages",
        json={
            "text": (
                'Add a /contact page with the heading "Contact us" and a form with Name, Email, '
                "and Message fields and a Submit button. Add a link to it in the main navigation."
            )
        },
    ).json()
    wait_status(client, posted["runId"], {"completed", "failed"}, timeout=180)
    finished = wait_until(lambda: (db.get("task", posted["taskId"]) or {}).get("status") in {"completed", "failed"}, timeout=1800)
    assert (db.get("task", posted["taskId"]) or {}).get("status") == "completed"
    assert finished
    folder = Path(project["folderPath"])
    blob = ""
    for path in folder.rglob("*"):
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts:
            blob += path.read_text(errors="ignore")
    assert "Contact us" in blob
    kids = [item for item in db.listing("task") if item.get("parentTaskId") == posted["taskId"] and not item.get("supersededBy")]
    assert kids
    assert all(not (db.get("agent", item.get("assignedAgentId") or "") or {}).get("roleKey") in {"team-lead", "qa-engineer"} for item in kids)
    assert all(board.last_handoff(item) for item in kids)
    assert all(board.handoff_covers_criteria(item, board.last_handoff(item)) for item in kids)
    assert any(item.get("engine") == "openhands" for item in db.listing("run") if item.get("kind") == "worker")
    reviews = [item for item in db.listing("run") if item.get("projectId") == project["id"] and item.get("kind") == "review"]
    assert any(item.get("agentId") == lead["id"] for item in reviews)
    assert any(item.get("agentId") == qa["id"] for item in reviews)
    rows = client.get(f"/projects/{project['id']}/messages").json()
    agent_text = " ".join((item.get("text") or "").lower() for item in rows if item.get("role") == "agent")
    assert "please proceed" not in agent_text
    assert "please execute" not in agent_text
