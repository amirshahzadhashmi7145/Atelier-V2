import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway import openai_gateway
from runtime.tools import dispatch
from store import db

from test_engine import client, fresh, ready  # noqa: F401


def _done():
    return {
        "tool_calls": [
            {
                "id": "done",
                "name": "complete",
                "arguments": {"summary": {"description": "Done.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def test_two_quick_messages_queue_the_second(client: TestClient):
    agent_id = ready(client)
    openai_gateway.SCRIPTS.append({"tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": "sleep 2"}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    project = client.post("/projects", json={"name": "Queue", "agentId": agent_id}).json()
    first = client.post(f"/projects/{project['id']}/messages", json={"text": "start work"}).json()
    second = client.post(f"/projects/{project['id']}/messages", json={"text": "second task"}).json()
    assert first["runId"] != second["runId"]
    runs = [client.get(f"/runs/{first['runId']}").json(), client.get(f"/runs/{second['runId']}").json()]
    statuses = {item["status"] for item in runs}
    assert "running" in statuses
    assert "queued" in statuses
    assert second.get("statusNote") == "queued, will start after the current task"


def test_stop_word_stops_active_and_clears_queue(client: TestClient):
    agent_id = ready(client)
    openai_gateway.SCRIPTS.append({"tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": "sleep 5"}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Stop", "agentId": agent_id}).json()
    client.post(f"/projects/{project['id']}/messages", json={"text": "go"})
    client.post(f"/projects/{project['id']}/messages", json={"text": "wait in line"})
    stop = client.post(f"/projects/{project['id']}/messages", json={"text": "stop"}).json()
    assert "runId" not in stop
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert rows[-1]["text"] == "stopped"


def test_follow_up_receives_prior_context(client: TestClient):
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Follow", "agentId": agent_id}).json()
    openai_gateway.SCRIPTS.append({"content": "fail", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600000}})
    failed = client.post(f"/projects/{project['id']}/messages", json={"text": "build page"}).json()
    deadline = time.time() + 10
    while time.time() < deadline:
        run = client.get(f"/runs/{failed['runId']}").json()
        if run["status"] == "failed":
            break
        time.sleep(0.05)
    openai_gateway.SCRIPTS.clear()
    openai_gateway.SCRIPTS.append(_done())
    follow = client.post(f"/projects/{project['id']}/messages", json={"text": "complete it"}).json()
    assert follow.get("runId")
    assert db.get("run", follow["runId"]).get("priorContext")


def test_files_edit_and_write_hash(client: TestClient, tmp_path):
    agent_id = ready(client)
    folder = tmp_path / "ws"
    folder.mkdir()
    run = {"id": "run_edit", "agentId": agent_id, "folder": str(folder)}
    (folder / "a.txt").write_text("hello")
    edited = dispatch(run, "files", {"op": "edit", "path": "a.txt", "old_text": "hello", "new_text": "hi"}, lambda: False)
    assert edited["changed"]
    assert (folder / "a.txt").read_text() == "hi"
    wrote = dispatch(run, "files", {"op": "write", "path": "b.txt", "content": "new"}, lambda: False)
    assert "hash" in wrote and wrote["size"] == 3


def test_files_edit_without_new_text_is_refused_not_destructive(client: TestClient, tmp_path):
    """Gemini sent `content` instead of `new_text`; the old code wiped the file and said changed=True."""
    agent_id = ready(client)
    folder = tmp_path / "ws"
    folder.mkdir()
    run = {"id": "run_edit2", "agentId": agent_id, "folder": str(folder)}
    (folder / "package.json").write_text('{"name": "x"}\n')
    result = dispatch(run, "files", {"op": "edit", "path": "package.json", "old_text": '{"name": "x"}', "content": "{}"}, lambda: False)
    assert result["refused"] and "new_text" in result["reason"]
    assert (folder / "package.json").read_text() == '{"name": "x"}\n'
    missing = dispatch(run, "files", {"op": "edit", "path": "package.json", "old_text": "nope", "new_text": "x"}, lambda: False)
    assert missing["changed"] is False and "not found" in missing["output"]


def test_build_test_survives_broken_package_json_and_names_missing_scripts(client: TestClient, tmp_path):
    from runtime import tools

    agent_id = ready(client)
    folder = tmp_path / "ws"
    folder.mkdir()
    run = {"id": "run_build_bad", "agentId": agent_id, "folder": str(folder)}
    (folder / "package.json").write_text("\n")
    broken = tools._build(run, folder, lambda: False)
    assert broken["buildOk"] is False and "not valid JSON" in broken["output"]
    (folder / "package.json").write_text('{"scripts": {"test": "node -e 0"}}')
    partial = tools._build(run, folder, lambda: False)
    assert partial["buildOk"] is False and 'no "build" script' in partial["output"]


def test_full_write_nudge_and_third_fails(client: TestClient):
    agent_id = ready(client)
    for version in ("v1", "v2", "v3"):
        call = {"id": "w", "name": "files", "arguments": {"op": "write", "path": "src/a.txt", "content": version}}
        openai_gateway.SCRIPTS.append({"tool_calls": [call], "usage": {"input_tokens": 1, "output_tokens": 1}})
    client.patch(f"/agents/{agent_id}", json={"scope": {"does": ["ui"], "neverDoes": [], "zones": ["src/**"]}})
    project = client.post("/projects", json={"name": "Rewrite", "agentId": agent_id}).json()
    (Path(project["folderPath"]) / "src").mkdir(parents=True)
    (Path(project["folderPath"]) / "src/a.txt").write_text("old")
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "rewrite"}).json()
    run = client.get(f"/runs/{message['runId']}").json()
    deadline = time.time() + 10
    while time.time() < deadline and run["status"] not in ("failed", "completed"):
        time.sleep(0.05)
        run = client.get(f"/runs/{message['runId']}").json()
    assert run["status"] == "failed"
    assert "rewrote" in next(item["payload"]["text"] for item in db.events_for(message["runId"]) if item["type"] == "RUN_FAILED")


def test_auto_build_after_three_writes(client: TestClient):
    agent_id = ready(client)
    write = {"id": "w", "name": "files", "arguments": {"op": "write", "path": "src/x.txt", "content": "a"}}
    for index in range(3):
        openai_gateway.SCRIPTS.append(
            {"tool_calls": [{**write, "arguments": {"op": "write", "path": f"src/x{index}.txt", "content": "a"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
        )
    openai_gateway.SCRIPTS.append(_done())
    client.patch(f"/agents/{agent_id}", json={"scope": {"does": ["ui"], "neverDoes": [], "zones": ["src/**"]}})
    project = client.post("/projects", json={"name": "Autobuild", "agentId": agent_id}).json()
    (Path(project["folderPath"]) / "src").mkdir(parents=True)
    (Path(project["folderPath"]) / "package.json").write_text('{"name":"x","scripts":{"build":"node -e \\"process.exit(0)\\"","test":"node -e \\"process.exit(0)\\""}}')
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "write files"}).json()
    deadline = time.time() + 15
    while time.time() < deadline:
        run = client.get(f"/runs/{message['runId']}").json()
        if run["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    logs = [item for item in db.listing("artifact") if item.get("runId") == message["runId"] and item["kind"] == "log"]
    assert logs


def test_complete_refused_without_build(client: TestClient):
    agent_id = ready(client)
    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "done",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Done.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    project = client.post("/projects", json={"name": "Nobuild", "agentId": agent_id}).json()
    (Path(project["folderPath"]) / "package.json").write_text('{"name":"x","scripts":{"build":"node -e \\"process.exit(1)\\"","test":"node -e \\"process.exit(0)\\""}}')
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "ship"}).json()
    deadline = time.time() + 10
    while time.time() < deadline:
        run = client.get(f"/runs/{message['runId']}").json()
        if run["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert any(item["type"] == "TOOL_REFUSED" for item in db.events_for(message["runId"]))


def test_read_outside_zones_write_refused_run_continues(client: TestClient):
    agent_id = ready(client)
    client.patch(f"/agents/{agent_id}", json={"scope": {"does": ["ui"], "neverDoes": [], "zones": ["src/**"]}})
    project = client.post("/projects", json={"name": "Zones", "agentId": agent_id}).json()
    folder = Path(project["folderPath"])
    (folder / "server").mkdir()
    (folder / "server/x.txt").write_text("secret")
    run = {"id": "z", "agentId": agent_id, "folder": str(folder)}
    read = dispatch(run, "files", {"op": "read", "path": "server/x.txt"}, lambda: False)
    assert "secret" in read["output"]
    bad = dispatch(run, "files", {"op": "write", "path": "server/y.txt", "content": "n"}, lambda: False)
    assert bad["refused"]
    openai_gateway.SCRIPTS.append({"tool_calls": [{"id": "r", "name": "files", "arguments": {"op": "read", "path": "server/x.txt"}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "read server"}).json()
    run_row = client.get(f"/runs/{message['runId']}").json()
    deadline = time.time() + 10
    while time.time() < deadline and run_row["status"] not in ("completed", "failed"):
        time.sleep(0.05)
        run_row = client.get(f"/runs/{message['runId']}").json()
    assert run_row["status"] == "completed"


def test_untracked_file_in_diff(client: TestClient, tmp_path):
    agent_id = ready(client)
    folder = tmp_path / "gitproj"
    folder.mkdir()
    import subprocess

    subprocess.run(["git", "init"], cwd=folder, capture_output=True)
    run = {"id": "diff", "agentId": agent_id, "folder": str(folder)}
    dispatch(run, "files", {"op": "write", "path": "new.txt", "content": "hi"}, lambda: False)
    diff = db.get("diff", "diff")
    assert any(item["path"] == "new.txt" for item in diff["files"])


def test_load_skill_idempotent(client: TestClient):
    agent_id = ready(client)
    skill = client.post("/skills", json={"name": "once", "description": "d", "body": "rules"}).json()
    client.patch(f"/agents/{agent_id}", json={"skillIds": [skill["id"]]})
    run = {"id": "skillrun", "agentId": agent_id, "folder": str(Path(client.post("/projects", json={"name": "Sk", "agentId": agent_id}).json()["folderPath"]))}
    first = dispatch(run, "load_skill", {"name": "once"}, lambda: False)
    second = dispatch(run, "load_skill", {"name": "once"}, lambda: False)
    assert "rules" in first["output"]
    assert second["output"] == "already loaded"


def test_oversized_skill_refused(client: TestClient):
    body = "word " * 9000
    response = client.post("/skills", json={"name": "big", "description": "d", "body": body})
    assert response.status_code == 422
    assert "data source" in response.json()["message"]


def test_model_call_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    agent_id = ready(client)
    monkeypatch.setenv("MOCK_MODEL_HANG", "1")
    monkeypatch.setenv("MODEL_FIRST_TOKEN_S", "0.05")
    project = client.post("/projects", json={"name": "Timeout", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "hang"}).json()
    deadline = time.time() + 8
    while time.time() < deadline:
        run = client.get(f"/runs/{message['runId']}").json()
        if run["status"] == "failed":
            break
        time.sleep(0.05)
    assert run["status"] == "failed"
    assert any(item["type"] == "MODEL_RETRY" for item in db.events_for(message["runId"]))


def test_no_progress_stop(client: TestClient):
    agent_id = ready(client)
    read = {"id": "r", "name": "search_data", "arguments": {"query": "x"}}
    for _ in range(16):
        openai_gateway.SCRIPTS.append({"tool_calls": [read], "usage": {"input_tokens": 1, "output_tokens": 1}})
    project = client.post("/projects", json={"name": "Stale", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "spin"}).json()
    deadline = time.time() + 12
    while time.time() < deadline:
        run = client.get(f"/runs/{message['runId']}").json()
        if run["status"] == "failed":
            break
        time.sleep(0.05)
    text = next(item["payload"]["text"] for item in db.events_for(message["runId"]) if item["type"] == "RUN_FAILED")
    assert "no progress" in text


def test_daily_cap_blocks_new_runs(client: TestClient):
    agent_id = ready(client)
    from runtime import project_runs

    project = client.post("/projects", json={"name": "Cap", "agentId": agent_id}).json()
    db.put("project-spend", project["id"], {"day": db.now()[:10], "usd": 25})
    client.put("/settings/runs", json={"maxSpendPerDayUsd": 20})
    response = client.post(f"/projects/{project['id']}/messages", json={"text": "blocked"})
    assert response.status_code == 429
    project_runs.add_spend(project["id"], 0)
