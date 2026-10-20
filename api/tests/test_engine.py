import os
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

os.environ["GATEWAY_MOCK"] = "1"
os.environ["FORCE_LOCAL"] = "1"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["PROJECTS_DIR"] = "/tmp/agent-studio-projects"

from app.main import app  # noqa: E402
from gateway import mock_turns, openai_gateway  # noqa: E402
from runtime.route_task import route_task  # noqa: E402
from runtime.sandbox import guard_path  # noqa: E402
from runtime.tools import dispatch  # noqa: E402
from store import db  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)


def _cancel_live_runs() -> None:
    try:
        from runtime.loop import wake
        from runtime.project_runs import ACTIVE

        for run in db.listing("run"):
            if run.get("status") not in ACTIVE:
                continue
            run["status"] = "cancelled"
            run["endedAt"] = db.now()
            db.put("run", run["id"], run)
            wake(run["id"])
        deadline = time.time() + 1.5
        while time.time() < deadline:
            live = [item for item in db.listing("run") if item.get("status") in ("running", "waiting_client", "waiting_user")]
            if not live:
                return
            time.sleep(0.05)
    except Exception:
        return


def _restore_github_origin() -> None:
    root = ROOT
    script = root / "scripts" / "ensure_origin.sh"
    if script.is_file():
        subprocess.run(["bash", str(script)], cwd=root, capture_output=True, check=False)


@pytest.fixture(autouse=True, scope="session")
def keep_github_origin():
    _restore_github_origin()
    yield
    _restore_github_origin()


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    _cancel_live_runs()
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ["PROJECTS_DIR"] = str(tmp_path / "projects")
    os.environ["GATEWAY_MOCK"] = "1"
    os.environ["FORCE_LOCAL"] = "1"
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    db.reset_engine()
    openai_gateway.SCRIPTS.clear()
    openai_gateway.PROMPTS.clear()
    mock_turns._defaults = 0
    openai_gateway.begin()
    os.environ.pop("STREAM_PACE_MS", None)
    from store import live

    live.reset()
    from runtime.openhands.client import set_client_factory

    set_client_factory(None)
    yield
    set_client_factory(None)
    _cancel_live_runs()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def ready(client: TestClient) -> str:
    agent = client.post(
        "/agents",
        json={
            "name": "Frontend",
            "roleKey": "frontend",
            "toolIds": ["files", "shell", "package_install"],
            "zones": ["."],
            "scope": {
                "does": ["user interfaces", "client-side state", "calling an existing API"],
                "neverDoes": ["servers", "databases", "API implementation", "auth backends", "infrastructure"],
                "zones": [],
            },
        },
    ).json()
    version = client.post(
        f"/agents/{agent['id']}/versions",
        json={"sections": {"role": "Role", "goal": "Goal", "instructions": "Work", "constraints": "Stay", "output": "Done"}},
    ).json()
    activated = client.post(f"/agents/{agent['id']}/versions/{version['version']}/activate")
    assert activated.status_code == 200
    return agent["id"]


def wait_status(client: TestClient, run_id: str, wanted: set[str], timeout: float = 8) -> dict:
    deadline = time.time() + timeout
    run = {}
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in wanted:
            return run
        time.sleep(0.05)
    return run


def test_contract_covers_openapi():
    spec = yaml.safe_load((ROOT / "openapi" / "agent-studio.yaml").read_text())
    expected = set()
    for path, methods in spec["paths"].items():
        for method in methods:
            if method in ("get", "post", "put", "patch", "delete"):
                expected.add((method.upper(), path))
    actual = set()
    for route in app.routes:
        targets = [route]
        original = getattr(route, "original_router", None)
        if original is not None:
            targets = original.routes
        for target in targets:
            methods = getattr(target, "methods", set()) or set()
            path = getattr(target, "path", None)
            for method in methods:
                if path and method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    actual.add((method, path))
    assert expected <= actual


def test_sse_resume_has_no_duplicates(client: TestClient):
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Build"}).json()
    assert wait_status(client, run["id"], {"completed"})["status"] == "completed"
    body = client.get(f"/runs/{run['id']}/events").text
    seqs = [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]
    assert seqs == list(range(1, len(seqs) + 1))
    resumed = client.get(f"/runs/{run['id']}/events", params={"after": 1}).text
    resumed_seqs = [int(line.removeprefix("id: ")) for line in resumed.splitlines() if line.startswith("id: ")]
    assert 1 not in resumed_seqs
    assert resumed_seqs[0] == 2


def test_stop_within_two_seconds(client: TestClient):
    openai_gateway.SCRIPTS.append(
        {"tool_calls": [{"id": "1", "name": "shell", "arguments": {"command": "sleep 30"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Wait"}).json()
    assert wait_status(client, run["id"], {"running"}, timeout=3)["status"] == "running"
    started = time.time()
    client.post(f"/runs/{run['id']}/stop")
    assert wait_status(client, run["id"], {"cancelled"}, timeout=2)["status"] == "cancelled"
    assert time.time() - started < 2


def test_answer_resumes(client: TestClient):
    openai_gateway.SCRIPTS.append(
        {"tool_calls": [{"id": "1", "name": "raise_clarification", "arguments": {"question": "Which label?"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "2",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Used Go.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Ask"}).json()
    assert wait_status(client, run["id"], {"waiting_user"})["status"] == "waiting_user"
    assert client.post(f"/runs/{run['id']}/answer", json={"text": "Go"}).status_code == 200
    finished = wait_status(client, run["id"], {"completed"})
    assert finished["status"] == "completed"
    assert finished["summary"]["description"] == "Used Go."


def test_path_guard(tmp_path: Path):
    with pytest.raises(PermissionError):
        guard_path(tmp_path, "../outside.txt")


def test_allow_list_refusal(client: TestClient):
    openai_gateway.SCRIPTS.append(
        {"tool_calls": [{"id": "1", "name": "package_install", "arguments": {"name": "vue"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Install"}).json()
    assert wait_status(client, run["id"], {"completed", "failed"})["status"] == "completed"
    body = client.get(f"/runs/{run['id']}/events").text
    assert "TOOL_REFUSED" in body
    assert "vue" in body


def test_react_stack_allows_lucide_and_tailwind_globs(client: TestClient):
    from runtime.tools import _package_allowed

    react = yaml.safe_load((ROOT / "stacks" / "react.yaml").read_text())
    nextjs = yaml.safe_load((ROOT / "stacks" / "nextjs.yaml").read_text())
    assert "lucide-react" in react["packageAllowList"]
    assert "lucide-react" in nextjs["packageAllowList"]
    agent_id = ready(client)
    stack = client.post(
        "/stacks",
        json={"name": "React", "version": "19", "packageAllowList": ["react", "lucide-react", "@tailwindcss/*"]},
    ).json()
    client.patch(f"/agents/{agent_id}", json={"stackIds": [stack["id"]]})
    agent = db.get("agent", agent_id)
    assert _package_allowed(agent, "lucide-react")
    assert _package_allowed(agent, "@tailwindcss/postcss")
    assert not _package_allowed(agent, "vue")
    db.put("stack", "react", {"id": "react", "packageAllowList": ["react"], "enabledByDefault": True})
    db.sync_stack_allow_lists()
    client.patch(f"/agents/{agent_id}", json={"stackIds": ["react"]})
    assert _package_allowed(db.get("agent", agent_id), "lucide-react")


def test_spend_cap_stops_the_run(client: TestClient):
    openai_gateway.SCRIPTS.append({"content": "thinking", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600000}})
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Spend"}).json()
    finished = wait_status(client, run["id"], {"failed"})
    assert finished["status"] == "failed"
    assert finished["terminalCause"] == "budget"


def _done() -> dict:
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


def test_loop_detection(client: TestClient):
    call = {"id": "1", "name": "files", "arguments": {"op": "write", "path": "a.txt", "content": "same"}}
    for _ in range(3):
        openai_gateway.SCRIPTS.append({"tool_calls": [call], "usage": {"input_tokens": 1, "output_tokens": 1}})
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Loop", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "write a.txt again"}).json()
    finished = wait_status(client, message["runId"], {"failed"})
    assert finished["status"] == "failed"
    assert finished["terminalCause"] == "loop"
    reply = client.get(f"/projects/{project['id']}/messages").json()[-1]
    assert reply["role"] == "agent" and reply["runId"] == message["runId"]
    assert reply["text"] != "The same tool call repeated."
    assert "writing a.txt" in reply["text"]
    assert "Cause: the same tool call repeated" in reply["text"]
    nudged = "\n".join(item.get("content") or "" for batch in openai_gateway.PROMPTS for item in batch)
    assert "you already ran this; change approach" in nudged
    first = "\n".join(item.get("content") or "" for item in openai_gateway.PROMPTS[0])
    assert "you already ran this; change approach" not in first


def test_reads_do_not_loop_and_the_first_repeat_only_nudges(client: TestClient):
    read = {"id": "r", "name": "files", "arguments": {"op": "read", "path": "a.txt"}}
    for _ in range(4):
        openai_gateway.SCRIPTS.append({"tool_calls": [read], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Read"}).json()
    assert wait_status(client, run["id"], {"completed", "failed"})["status"] == "completed"
    write = {"id": "w", "name": "files", "arguments": {"op": "write", "path": "b.txt", "content": "same"}}
    for _ in range(2):
        openai_gateway.SCRIPTS.append({"tool_calls": [write], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    again = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Nudge"}).json()
    assert wait_status(client, again["id"], {"completed", "failed"})["status"] == "completed"
    last = "\n".join(item.get("content") or "" for item in openai_gateway.PROMPTS[-1])
    assert "you already ran this; change approach" in last


def test_shell_repeats_only_when_the_result_matches(client: TestClient):
    for command in ("echo one", "echo two", "echo one"):
        openai_gateway.SCRIPTS.append({"tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": command}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(_done())
    mixed = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Echo"}).json()
    assert wait_status(client, mixed["id"], {"completed", "failed"})["status"] == "completed"
    for _ in range(3):
        openai_gateway.SCRIPTS.append({"tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": "echo hi"}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    repeated = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Echo hi"}).json()
    finished = wait_status(client, repeated["id"], {"failed"})
    assert finished["terminalCause"] == "loop"
    text = next(item["payload"]["text"] for item in db.events_for(repeated["id"]) if item["type"] == "RUN_FAILED")
    assert text != "The same tool call repeated."
    assert "running echo hi" in text
    assert "Cause: the same tool call repeated" in text


def test_chat_names_enabled_stacks_and_refuses_node(client: TestClient):
    from runtime.classify import chat_system

    agent_id = ready(client)
    react = client.post("/stacks", json={"name": "React", "version": "19", "scaffoldTemplate": "vite-react-ts"}).json()
    client.post("/stacks", json={"name": "Next", "version": "15", "scaffoldTemplate": "next"})
    client.patch(f"/agents/{agent_id}", json={"stackIds": [react["id"]]})
    system = chat_system(db.get("agent", agent_id))
    assert "# Tools" not in system
    assert "# Enabled stacks" in system and "React" in system and "# Skills" in system and "# Scope" in system
    project = client.post("/projects", json={"name": "Ask", "agentId": agent_id}).json()
    tech = client.post(f"/projects/{project['id']}/messages", json={"text": "what tech can you work with"}).json()
    assert "runId" not in tech
    reply = client.get(f"/projects/{project['id']}/messages").json()[-1]["text"]
    assert "React" in reply and "Next" not in reply
    node = client.post(f"/projects/{project['id']}/messages", json={"text": "can you do Node"}).json()
    assert "runId" not in node
    answer = client.get(f"/projects/{project['id']}/messages").json()[-1]["text"]
    assert answer.lower().startswith("no")
    assert "Backend Engineer" in answer
    assert client.get("/runs").json()["total"] == 0


def test_refusal_falls_back_when_the_model_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from runtime import classify

    monkeypatch.setenv("GATEWAY_MOCK", "0")

    def boom(*_args, **_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(openai_gateway, "complete", boom)
    agent = db.get("agent", ready(client))
    text = classify.refusal(agent, "build the backend")
    assert text == "That is outside my role. I can do user interfaces, client-side state, calling an existing API. Add an agent for that role."


def test_empty_project_runs_the_scaffold_command(client: TestClient):
    agent_id = ready(client)
    stack = client.post(
        "/stacks",
        json={"name": "Hono", "version": "4", "scaffoldTemplate": "python3 -c \"open('from-scaffold.txt','w').write('yes')\""},
    ).json()
    client.patch(f"/agents/{agent_id}", json={"stackIds": [stack["id"]]})
    openai_gateway.SCRIPTS.append(_done())
    project = client.post("/projects", json={"name": "Fresh", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "add a page"}).json()
    assert wait_status(client, message["runId"], {"completed", "failed"})["status"] == "completed"
    assert (Path(project["folderPath"]) / "from-scaffold.txt").read_text() == "yes"
    first = "\n".join(item.get("content") or "" for item in openai_gateway.PROMPTS[0])
    assert "The scaffold already exists" in first
    assert "Do not run a create command." in first


def test_tic_tac_toe_ui_reaches_a_built_app_with_screenshots(client: TestClient):
    from runtime.tools import _png_matches

    agent_id = ready(client)
    stack = client.post("/stacks", json={"name": "React", "version": "19", "scaffoldTemplate": "vite-react-ts"}).json()
    client.patch(
        f"/agents/{agent_id}",
        json={"stackIds": [stack["id"]], "toolIds": ["files", "shell", "package_install", "build_test", "headless_browser"]},
    )
    project = client.post("/projects", json={"name": "Game", "agentId": agent_id}).json()
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "make me a tic tac toe UI"}).json()
    assert message["runId"]
    assert db.get("task", message["taskId"])["label"] == "task"
    finished = wait_status(client, message["runId"], {"completed", "failed"}, timeout=90)
    assert finished["status"] == "completed", finished.get("terminalCause")
    folder = Path(project["folderPath"])
    assert "Tic Tac Toe" in (folder / "index.html").read_text()
    logs = [item for item in db.listing("artifact") if item.get("runId") == message["runId"] and item["kind"] == "log"]
    assert logs and logs[-1]["ok"]
    for name, width, height in (("mobile", 390, 844), ("tablet", 768, 1024), ("desktop", 1280, 800)):
        assert _png_matches(folder / ".artifacts" / f"{name}.png", width, height)
    first = "\n".join(item.get("content") or "" for item in openai_gateway.PROMPTS[0])
    assert "The scaffold already exists (vite-react-ts)." in first


def test_route_task_assigns_the_only_member():
    task = {"assignedAgentId": "", "routedBy": ""}
    route_task({"members": ["agt_7"]}, task)
    assert task["assignedAgentId"] == "agt_7"
    assert task["routedBy"] == "user"


def test_supervisor_tools_refused_for_a_normal_agent(client: TestClient):
    agent_id = ready(client)
    refused = dispatch({"id": "local", "agentId": agent_id}, "create_task", {"text": "review this"}, lambda: False)
    assert refused["refused"] is True
    review = dispatch({"id": "local", "agentId": agent_id}, "record_review", {"taskId": "t", "verdict": "approve", "notes": "ok"}, lambda: False)
    assert review["refused"] is True


def test_deltas_merge_into_one_output(client: TestClient):
    os.environ["STREAM_PACE_MS"] = "80"
    openai_gateway.SCRIPTS.append(
        {
            "content": "alpha beta gamma delta epsilon zeta",
            "tool_calls": [{"id": "s", "name": "shell", "arguments": {"command": "sleep 1"}}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "2",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Done.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Stream"}).json()
    assert wait_status(client, run["id"], {"completed"})["status"] == "completed"
    assert not any(item["type"] == "MODEL_DELTA" for item in db.events_for(run["id"]))
    final = db.events_for(run["id"])
    assert not any(item["type"] == "MODEL_DELTA" for item in final)
    output = [item for item in final if item["type"] == "MODEL_OUTPUT"]
    assert len(output) >= 1
    assert "alpha beta" in output[0]["payload"]["text"]
    seqs = [item["seq"] for item in final]
    assert seqs == list(range(1, len(seqs) + 1))
    body = client.get(f"/runs/{run['id']}/events", params={"after": 1}).text
    resumed = [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]
    assert resumed == seqs[1:]


def test_interleaved_calls_keep_their_own_text(client: TestClient):
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "interleave-bubbles"}).json()
    assert wait_status(client, run["id"], {"completed"})["status"] == "completed"
    outputs = [item["payload"]["text"] for item in db.events_for(run["id"]) if item["type"] == "MODEL_OUTPUT"]
    assert outputs[:2] == ["First bubble.", "Second bubble."]
    assert not any(item["type"] == "MODEL_DELTA" for item in db.events_for(run["id"]))


def test_classifier_routes_chat_task_and_out(client: TestClient):
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Chat", "agentId": agent_id}).json()
    hello = client.post(f"/projects/{project['id']}/messages", json={"text": "hello"}).json()
    assert "runId" not in hello
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert rows[-1]["role"] == "agent"
    assert "without starting a run" in rows[-1]["text"]
    assert client.get("/runs").json()["total"] == 0
    task = client.post(f"/projects/{project['id']}/messages", json={"text": "Create a landing page with a hero"}).json()
    assert task["runId"]
    assert db.get("task", task["taskId"])["label"] == "task"
    outside = client.post(f"/projects/{project['id']}/messages", json={"text": "Deploy this on kubernetes"}).json()
    assert "runId" not in outside
    stored = db.get("task", outside["taskId"])
    assert stored["label"] == "out"
    assert "outside my role" in stored["summary"]
    assert wait_status(client, task["runId"], {"completed", "failed"}, timeout=20)["status"] == "completed"


def test_stop_preview_message_does_not_start_a_run(client: TestClient):
    from runtime.classify import is_control, is_preview_stop, label

    assert is_preview_stop("ok stop the preiew server")
    assert is_preview_stop("ok stop the preview server")
    assert not is_control("ok stop the preiew server")
    assert not is_control("stop the preview server")
    assert is_control("stop")
    assert label({}, "ok stop the preiew server") == "chat"
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Preview", "agentId": agent_id}).json()
    db.put("preview", project["id"], {"pid": 0, "url": "http://127.0.0.1:9"})
    message = client.post(f"/projects/{project['id']}/messages", json={"text": "ok stop the preiew server"}).json()
    assert "runId" not in message
    rows = client.get(f"/projects/{project['id']}/messages").json()
    assert rows[-1]["text"] == "Preview stopped."
    assert db.get("preview", project["id"]) is None
    assert client.get("/runs").json()["total"] == 0
    idle = client.post("/projects", json={"name": "Idle", "agentId": agent_id}).json()
    again = client.post(f"/projects/{idle['id']}/messages", json={"text": "stop the preview"}).json()
    assert "runId" not in again
    idle_rows = client.get(f"/projects/{idle['id']}/messages").json()
    assert idle_rows[-1]["text"] == "No preview is running."


def test_scope_refuses_backend_work_and_a_server_file(client: TestClient):
    agent_id = ready(client)
    client.patch(
        f"/agents/{agent_id}",
        json={"scope": {"does": ["user interfaces"], "neverDoes": ["servers", "databases"], "zones": ["web/**", "src/**", "public/**"]}},
    )
    preview = client.post(
        f"/agents/{agent_id}/compile-preview",
        json={
            "sections": {"role": "Role", "goal": "Goal", "instructions": "Work", "constraints": "Stay", "output": "Done"},
            "toolIds": ["files"],
            "skillIds": [],
            "stackIds": [],
            "scope": {"does": ["user interfaces"], "neverDoes": ["servers"], "zones": ["src/**"]},
        },
    ).json()
    assert "# Scope" in preview["compiled"]
    assert "You cannot enable stacks or change your own scope; only the user can." in preview["compiled"]
    project = client.post("/projects", json={"name": "Scope", "agentId": agent_id}).json()
    for text in ("build the backend", "work on nodejs", "add a database"):
        message = client.post(f"/projects/{project['id']}/messages", json={"text": text}).json()
        assert "runId" not in message
        assert db.get("task", message["taskId"])["label"] == "out"
        reply = client.get(f"/projects/{project['id']}/messages").json()[-1]
        assert reply["text"].startswith("That is outside my role.")
        assert "Add an agent for that role" in reply["text"]
    game = client.post(f"/projects/{project['id']}/messages", json={"text": "build a tic tac toe game"}).json()
    assert game["runId"]
    assert db.get("task", game["taskId"])["label"] == "task"
    assert wait_status(client, game["runId"], {"completed", "failed"}, timeout=20)["status"] == "completed"
    openai_gateway.SCRIPTS.append(
        {"tool_calls": [{"id": "w", "name": "files", "arguments": {"op": "write", "path": "server/index.js", "content": "listen"}}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    )
    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "done",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Tried.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    run = client.post("/runs", json={"agentId": agent_id, "workspace": {"kind": "scaffold", "template": "local"}, "task": "Write the server"}).json()
    assert wait_status(client, run["id"], {"completed", "failed"})["status"] == "completed"
    refused = [item for item in db.events_for(run["id"]) if item["type"] == "TOOL_REFUSED"]
    assert refused and "server/index.js" in refused[0]["payload"]["reason"]


def test_shell_timeout_is_reported_and_daemons_are_refused(client: TestClient):
    from runtime import sandbox, tools

    code, output = sandbox.run_command(Path("."), "sleep 5", lambda: False, timeout=0.3)
    assert code == 1
    assert output == "timed out"
    refused = tools._shell(Path("."), "npm run dev", lambda: False)
    assert refused["refused"] is True
    assert "preview" in refused["reason"]


def test_clarification_is_capped_at_one_round(client: TestClient):
    questions = {"id": "q", "name": "raise_clarification", "arguments": {"questions": ["one", "two", "three", "four"]}}
    openai_gateway.SCRIPTS.append({"tool_calls": [questions], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append({"tool_calls": [questions], "usage": {"input_tokens": 1, "output_tokens": 1}})
    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "2",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Done.", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Ask"}).json()
    paused = wait_status(client, run["id"], {"waiting_user"})
    raised = [item for item in db.events_for(run["id"]) if item["type"] == "CLARIFICATION_RAISED"][-1]
    assert raised["payload"]["question"].count("\n") == 2
    assert "four" not in raised["payload"]["question"]
    project = client.post("/projects", json={"name": "Answers", "agentId": ready(client)}).json()
    db.put("run", run["id"], {**db.get("run", run["id"]), "projectId": project["id"]})
    client.post(f"/runs/{run['id']}/answer", json={"text": "use the first option"})
    finished = wait_status(client, run["id"], {"completed"})
    assert "Proceeding with assumption" in finished["summary"]["assumptions"][0]
    assert any(item["role"] == "user" and item["text"] == "use the first option" for item in client.get(f"/projects/{project['id']}/messages").json())


def test_teach_creates_skill_stack_and_docs(client: TestClient):
    agent_id = ready(client)
    result = client.post(
        f"/agents/{agent_id}/teach",
        json={"name": "Hono", "version": "4", "rules": "Use the context helper.", "docsUrl": "https://hono.dev", "packages": ["hono"], "scaffold": "npm create hono"},
    )
    assert result.status_code == 201
    body = result.json()
    assert body["skill"]["name"] == "Hono"
    assert body["dataSource"]["ref"] == "https://hono.dev"
    agent = client.get(f"/agents/{agent_id}").json()
    assert body["skill"]["id"] in agent["skillIds"]
    assert body["stack"]["id"] in agent["stackIds"]
    draft = client.post(f"/agents/{agent_id}/teach/draft", json={"repoUrl": "https://example.com/demo.git"})
    assert "example.com/demo.git" in draft.json()["rules"]


def test_empty_screenshot_fails(tmp_path):
    from runtime import evals, tools

    empty = tmp_path / "desktop.png"
    empty.write_bytes(b"")
    assert tools._png_matches(empty, 1280, 800) is False
    png = bytearray(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    png[16:20] = (1280).to_bytes(4, "big")
    png[20:24] = (800).to_bytes(4, "big")
    assert tools._png_matches(tmp_path / "missing.png", 1280, 800) is False
    real = tmp_path / "desktop.png"
    real.write_bytes(png)
    assert tools._png_matches(real, 1280, 800) is False
    real.write_bytes(bytes(png) + b"\x00" * 80)
    assert tools._png_matches(real, 1280, 800) is True
    hidpi = bytearray(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    hidpi[16:20] = (2560).to_bytes(4, "big")
    hidpi[20:24] = (1600).to_bytes(4, "big")
    two = tmp_path / "hidpi.png"
    two.write_bytes(bytes(hidpi) + b"\x00" * 80)
    assert tools._png_matches(two, 1280, 800) is True
    db.put("artifact", "art_1", {"id": "art_1", "runId": "run_x", "kind": "screenshot", "viewport": "desktop", "ok": False, "consoleErrors": []})
    status, evidence = evals.judge(
        {"id": "run_x", "status": "completed", "summary": {"description": "Done.", "criteria": [{"text": "Hero", "evidence": "shown"}]}},
        {"criteria": ["Hero"], "passRule": "screenshots"},
    )
    assert status == "fail"
    assert evidence == "screenshot unavailable"


def _eval_agent(client: TestClient, rule: str) -> tuple[str, int]:
    agent = client.post(
        "/agents",
        json={"name": "Eval", "roleKey": "frontend", "toolIds": ["files", "build_test", "headless_browser"]},
    ).json()
    assert client.post(
        f"/agents/{agent['id']}/evals",
        json={"name": "page", "task": "Ship a page", "criteria": ["Hero is visible"], "passRule": rule},
    ).status_code == 201
    version = client.post(
        f"/agents/{agent['id']}/versions",
        json={"sections": {"role": "Role", "goal": "Goal", "instructions": "Work", "constraints": "Stay", "output": "Done"}},
    ).json()
    return agent["id"], version["version"]


def test_eval_pass_rules(client: TestClient):
    agent_id, version = _eval_agent(client, "build_and_tests")
    ran = client.post(f"/agents/{agent_id}/versions/{version}/evals/run")
    assert ran.status_code == 200
    row = ran.json()["evalResults"][0]
    assert row["status"] == "pass"
    assert row["runId"]
    assert "costUsd" in row
    assert client.post(f"/agents/{agent_id}/versions/{version}/activate").status_code == 200

    shots = _eval_agent(client, "build_tests_and_screenshots")
    shot = client.post(f"/agents/{shots[0]}/versions/{shots[1]}/evals/run")
    assert shot.json()["evalResults"][0]["status"] == "fail"
    assert shot.json()["evalResults"][0]["evidence"] == "screenshot unavailable"

    openai_gateway.SCRIPTS.append(
        {
            "tool_calls": [
                {
                    "id": "1",
                    "name": "complete",
                    "arguments": {"summary": {"description": "Skipped the build.", "filesChanged": [], "dependencies": [], "criteria": [{"text": "Hero is visible", "evidence": "claimed"}], "assumptions": [], "followUps": []}},
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    failed_agent, failed_version = _eval_agent(client, "build_and_tests")
    failed = client.post(f"/agents/{failed_agent}/versions/{failed_version}/evals/run")
    assert failed.json()["evalResults"][0]["status"] == "fail"
    assert client.post(f"/agents/{failed_agent}/versions/{failed_version}/activate").status_code == 409

    client.put("/settings/runs", json={"maxSpendPerRunUsd": 0})
    capped_agent, capped_version = _eval_agent(client, "build_and_tests")
    capped = client.post(f"/agents/{capped_agent}/versions/{capped_version}/evals/run")
    assert capped.json()["evalResults"][0]["status"] == "fail"


def test_compare_evals_feed_model_stats(client: TestClient):
    agent_id, version = _eval_agent(client, "build_and_tests")
    assert client.post("/providers/openai/refresh").status_code == 200
    compared = client.post(f"/agents/{agent_id}/versions/{version}/evals/compare", json={"models": ["gpt-4.1-mini"]})
    assert compared.status_code == 200
    row = compared.json()["rows"][0]
    assert row["model"] == "gpt-4.1-mini"
    assert row["passRate"] == 1
    models = client.get("/models").json()
    match = next(item for item in models if item["name"] == "gpt-4.1-mini")
    assert any(item["roleKey"] == "frontend" and item["runs"] >= 1 and item["passed"] >= 1 for item in match["ownStats"])


def test_tiktoken_counts_the_compiled_prompt(client: TestClient):
    import tiktoken

    from runtime.compile import compile_prompt, token_count

    ready(client)
    text = "hello world"
    assert token_count(text, "gpt-4o") == len(tiktoken.encoding_for_model("gpt-4o").encode(text))
    compiled = compile_prompt({"role": "Role", "goal": "Goal", "instructions": "Work", "constraints": "Stay", "output": "Done"}, ["files"], [], [])
    assert compiled["tokenCount"] == token_count(compiled["compiled"], "gpt-4o")


def test_summary_after_21_messages_is_in_the_next_context(client: TestClient):
    from runtime.loop import _messages, refresh_summary

    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Memory", "agentId": agent_id}).json()
    for index in range(21):
        message_id = f"msg_{index}"
        db.put(
            "message",
            message_id,
            {"id": message_id, "projectId": project["id"], "role": "user", "text": f"note {index}", "createdAt": f"2026-01-01T00:00:{index:02d}Z"},
        )
    refresh_summary(project["id"], "gpt-4o")
    saved = client.get(f"/projects/{project['id']}").json()
    assert "note 0" in saved["summary"]
    messages = _messages({"id": "run", "agentId": agent_id, "task": "next", "projectId": project["id"], "model": {"name": "gpt-4o"}}, db.get("agent", agent_id), None)
    blob = "\n".join(item["content"] for item in messages)
    assert "Conversation so far:" in blob
    assert "note 0" in blob
    assert "Earlier messages omitted" not in blob


def test_proxy_blocks_a_disallowed_host():
    import socket

    from runtime.sandbox import ensure_proxy

    port = ensure_proxy()
    sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    sock.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    data = sock.recv(200)
    sock.close()
    assert b"403" in data


def test_docker_allow_list_blocks_a_disallowed_host(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FORCE_LOCAL", raising=False)
    from runtime import sandbox

    if sandbox.local_mode():
        pytest.skip("docker not available")
    (tmp_path / "check.js").write_text(
        "const net=require('net');"
        "const s=net.connect(8080, process.env.PROXY_HOST, ()=>{"
        "s.write('CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com\\r\\n\\r\\n');"
        "});"
        "s.on('data', (b)=>{console.log(String(b)); process.exit(String(b).includes('403')?0:1)});"
        "s.on('error', (e)=>{console.log(String(e)); process.exit(1)});"
    )
    code, output = sandbox.run_command(tmp_path, "node check.js", lambda: False)
    assert code == 0, output
    assert "403" in output


@pytest.mark.skipif(os.environ.get("RUN_GITHUB_TESTS") != "1", reason="set RUN_GITHUB_TESTS=1")
def test_github_branch_push_and_pr(client: TestClient):
    import httpx
    from dotenv import load_dotenv

    load_dotenv(ROOT / "api" / ".env")
    token = os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        pytest.skip("GITHUB_TOKEN is empty")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    created = httpx.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json={"name": f"atelier-s7-{int(time.time())}", "auto_init": True, "private": True},
        timeout=30,
    )
    assert created.status_code < 300
    full_name = created.json()["full_name"]
    try:
        agent_id = ready(client)
        project = client.post(
            "/projects",
            json={"name": "Ship", "agentId": agent_id, "repoUrl": created.json()["clone_url"], "githubToken": token},
        ).json()
        message = client.post(f"/projects/{project['id']}/messages", json={"text": "Create a landing page"}).json()
        finished = wait_status(client, message["runId"], {"completed", "failed"}, timeout=60)
        assert finished["status"] == "completed"
        assert finished.get("prUrl")
        messages = client.get(f"/projects/{project['id']}/messages").json()
        assert any(finished["prUrl"] in item["text"] for item in messages)
    finally:
        httpx.delete(f"https://api.github.com/repos/{full_name}", headers=headers, timeout=30)


@pytest.mark.skipif(os.environ.get("RUN_REAL_LLM_TESTS") != "1", reason="set RUN_REAL_LLM_TESTS=1 to call OpenAI")
def test_real_landing_page(client: TestClient):
    from dotenv import load_dotenv

    load_dotenv(ROOT / "api" / ".env")
    load_dotenv(ROOT / "web" / ".env.local")
    os.environ["GATEWAY_MOCK"] = "0"
    agent_id = ready(client)
    project = client.post("/projects", json={"name": "Landing", "agentId": agent_id}).json()
    message = client.post("/projects/" + project["id"] + "/messages", json={"text": "Create a landing page with a hero and three feature cards"}).json()
    finished = wait_status(client, message["runId"], {"completed", "failed"}, timeout=180)
    assert finished["status"] == "completed"
    assert finished["summary"]["description"]
    diff = client.get(f"/runs/{message['runId']}/diff").json()
    assert diff["files"]
    artifacts = client.get(f"/runs/{message['runId']}/artifacts").json()
    viewports = {item.get("viewport") for item in artifacts if item["kind"] == "screenshot"}
    assert {"mobile", "tablet", "desktop"} <= viewports
