from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runtime import board, notes
from runtime.loop import _messages
from runtime.openhands.client import FakeOpenHands, ProcessOpenHandsClient, RunSpec
from runtime.openhands.envcheck import IsolatedLitellmMismatch, PINNED_LITELLM, LOCK, REQUIREMENTS
from runtime.supervisor.nodes import advance
from runtime.tools import dispatch
from store import db

from test_engine import client, fresh  # noqa: F401
from test_s13_lead import lead_agent
from test_s17_openhands import _agent, _run, _workspace


def _notes_file(project: dict, text: str) -> Path:
    path = Path(project["folderPath"]) / notes.path_for(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_project_notes_settings_round_trip(client: TestClient):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "NotesSettings", "agentId": agent["id"]}).json()
    assert project["notesPath"] == ".atelier/NOTES.md"
    assert project["notesMaxBytes"] == 8192
    patched = client.patch(
        f"/projects/{project['id']}",
        json={"notesPath": "docs/NOTES.md", "notesMaxBytes": 1024},
    ).json()
    assert patched["notesPath"] == "docs/NOTES.md"
    assert patched["notesMaxBytes"] == 1024


def test_isolated_litellm_pin_matches_lock_and_requirements():
    req = REQUIREMENTS.read_text()
    lock = LOCK.read_text()
    assert f"litellm=={PINNED_LITELLM}" in req
    assert f"litellm=={PINNED_LITELLM}" in lock
    assert PINNED_LITELLM == "1.96.2"


def test_openhands_run_refused_when_isolated_litellm_is_wrong(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime.openhands.envcheck.probe_isolated_version", lambda: "1.93.0")
    runner = ProcessOpenHandsClient()
    with pytest.raises(IsolatedLitellmMismatch, match="1.93.0"):
        runner.run(
            RunSpec(
                workspace=tmp_path,
                prompt="x",
                model="openai/gpt-4.1-mini",
                api_key=None,
                mcp={},
                timeout_sec=5,
            )
        )


def test_notes_included_in_loop_and_openhands_task_input(client: TestClient):
    marker = "The REST API lives in api/app/routes.py"
    oh = _agent(client, engine="openhands", name="OH Notes")
    loop_agent = _agent(client, engine="loop", name="Loop Notes")
    project, task = _workspace(client, oh)
    _notes_file(project, f"# Project notes\n- {marker}\n")
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    _run(project, task, fake)
    prompt = fake.last_spec.prompt if fake.last_spec else ""
    assert marker in prompt
    assert ".atelier/NOTES.md" in prompt
    assert fake.last_spec and marker in (fake.last_spec.repo_instructions or "")

    loop_project = client.post("/projects", json={"name": "LoopNotes", "agentId": loop_agent["id"]}).json()
    folder = Path(loop_project["folderPath"])
    (folder / ".atelier").mkdir(parents=True, exist_ok=True)
    (folder / ".atelier" / "NOTES.md").write_text(f"# Project notes\n- {marker}\n")
    run = {
        "id": db.nid("run"),
        "agentId": loop_agent["id"],
        "projectId": loop_project["id"],
        "folder": str(folder),
        "task": "Add a heading",
        "kind": "worker",
        "promptVersionId": loop_agent.get("activePromptVersionId"),
    }
    blob = "\n".join(str(item.get("content") or "") for item in _messages(run, loop_agent, None))
    assert marker in blob
    assert "Project notes" in blob


def test_worker_edit_to_notes_file_is_rejected_by_zone_check(client: TestClient):
    agent = _agent(client, zones=["src/**", "package.json", ".atelier/**"])
    project, task = _workspace(client, agent)
    _notes_file(project, "# Project notes\n- stack is React\n")
    fake = FakeOpenHands(files={".atelier/NOTES.md": "# Project notes\n- worker wrote this\n", "src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake)
    assert result["handoffId"] is None
    feedback = board.latest_feedback(db.get("task", task["id"]))
    assert feedback
    assert "protected notes" in (feedback.get("notes") or "")

    run = {
        "id": db.nid("run"),
        "agentId": agent["id"],
        "projectId": project["id"],
        "folder": project["folderPath"],
        "kind": "worker",
        "task": "x",
    }
    wrote = dispatch(
        run,
        "files",
        {"op": "write", "path": ".atelier/NOTES.md", "content": "nope"},
        lambda: False,
    )
    assert wrote.get("refused")
    assert "notes file" in (wrote.get("reason") or "")


def test_supervisor_approval_adds_fact_and_records_on_board(client: TestClient):
    worker = _agent(client, engine="loop")
    lead = lead_agent(client)
    project, task = _workspace(client, worker)
    assert client.post(f"/projects/{project['id']}/members", json={"agentId": lead["id"]}).status_code == 200
    project = db.get("project", project["id"])
    parent = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": None,
        "text": "parent",
        "assignedAgentId": lead["id"],
        "routedBy": "user",
        "status": "running",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
        "acceptanceCriteria": [],
        "reworkCount": 0,
    }
    db.put("task", parent["id"], parent)
    task["parentTaskId"] = parent["id"]
    task["assignedAgentId"] = worker["id"]
    db.put("task", task["id"], task)
    handoff = board.write_handoff(
        {"agentId": worker["id"]},
        task,
        {
            "description": "FACT: The REST API lives in api/app/routes.py\nImplemented the hello heading and the tests passed.",
            "filesChanged": ["src/App.tsx"],
            "criteria": [{"text": "the heading is visible", "evidence": "src/App.tsx"}],
        },
    )
    board.write_feedback(task, lead, "approve", "Looks good", [])
    advance(
        {
            "project_id": project["id"],
            "parent_task_id": parent["id"],
            "supervisor_agent_id": lead["id"],
            "lead_run_id": "run_lead",
            "task_ids": [task["id"]],
            "status_by_task": {task["id"]: "reviewing"},
            "decision_ids": [],
            "handoff_ids": [handoff["id"]],
            "current_layer": 1,
            "current_task_id": task["id"],
            "current_reviewer_id": lead["id"],
            "phase": "advance",
        }
    )
    text = notes.read_text(project)
    assert "REST API lives in api/app/routes.py" in text
    assert "Implemented the hello heading" not in text
    events = [item for item in board.timeline(db.get("task", task["id"])) if item.get("kind") == "notes"]
    assert events
    assert "REST API" in (events[-1].get("summary") or "")
    viewed = client.get(f"/projects/{project['id']}/tasks/{task['id']}").json()
    assert any(item.get("kind") == "notes" for item in viewed.get("events") or [])


def test_task_progress_is_not_written_to_notes(client: TestClient):
    worker = _agent(client)
    project, task = _workspace(client, worker)
    board.write_handoff(
        {"agentId": worker["id"]},
        task,
        {"description": "Implemented the hello heading and the tests passed. Ready for review.", "filesChanged": ["src/App.tsx"]},
    )
    result = notes.update_after_approval(db.get("project", project["id"]), db.get("task", task["id"]))
    assert result is None
    assert notes.read_text(db.get("project", project["id"])) == ""


def test_notes_size_limit_triggers_shorter_rewrite(client: TestClient):
    worker = _agent(client)
    lead = lead_agent(client)
    project, task = _workspace(client, worker)
    project = db.get("project", project["id"])
    project["notesMaxBytes"] = 400
    db.put("project", project["id"], project)
    long_facts = "\n".join(f"- The stack uses library number {index} located in src/lib/{index}" for index in range(20))
    _notes_file(project, "# Project notes\n" + long_facts + "\n")
    before = len(notes.read_text(project).encode())
    assert before >= int(400 * notes.NEAR_LIMIT)
    board.write_handoff(
        {"agentId": worker["id"]},
        task,
        {"description": "FACT: Folder layout keeps UI under src/ and the API under api/.", "filesChanged": []},
    )
    board.write_feedback(task, lead, "approve", "ok", [])
    result = notes.update_after_approval(db.get("project", project["id"]), db.get("task", task["id"]))
    assert result and result.get("rewritten")
    after = notes.read_text(db.get("project", project["id"]))
    assert len(after.encode()) < before
    assert len(after.encode()) < 400
