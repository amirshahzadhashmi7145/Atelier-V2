import os
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
from gateway import openai_gateway  # noqa: E402
from runtime.route_task import route_task  # noqa: E402
from runtime.sandbox import guard_path  # noqa: E402
from runtime.tools import dispatch  # noqa: E402
from store import db  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ["PROJECTS_DIR"] = str(tmp_path / "projects")
    os.environ["GATEWAY_MOCK"] = "1"
    os.environ["FORCE_LOCAL"] = "1"
    db.reset_engine()
    openai_gateway.SCRIPTS.clear()
    openai_gateway._defaults = 0
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def ready(client: TestClient) -> str:
    agent = client.post(
        "/agents",
        json={"name": "Frontend", "roleKey": "frontend", "toolIds": ["files", "shell", "package_install"], "zones": ["."]},
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


def test_spend_cap_stops_the_run(client: TestClient):
    openai_gateway.SCRIPTS.append({"content": "thinking", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600000}})
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Spend"}).json()
    finished = wait_status(client, run["id"], {"failed"})
    assert finished["status"] == "failed"
    assert finished["terminalCause"] == "budget"


def test_loop_detection(client: TestClient):
    call = {"id": "1", "name": "files", "arguments": {"op": "write", "path": "a.txt", "content": "same"}}
    for _ in range(3):
        openai_gateway.SCRIPTS.append({"tool_calls": [call], "usage": {"input_tokens": 1, "output_tokens": 1}})
    run = client.post("/runs", json={"agentId": ready(client), "workspace": {"kind": "scaffold", "template": "local"}, "task": "Loop"}).json()
    finished = wait_status(client, run["id"], {"failed"})
    assert finished["status"] == "failed"
    assert finished["terminalCause"] == "loop"


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
