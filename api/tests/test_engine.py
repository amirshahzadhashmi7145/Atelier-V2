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
    openai_gateway.begin()
    os.environ.pop("STREAM_PACE_MS", None)
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
    seen: list[dict] = []
    deadline = time.time() + 5
    while time.time() < deadline:
        seen = db.events_for(run["id"])
        if any(item["type"] == "MODEL_DELTA" for item in seen):
            break
        time.sleep(0.01)
    deltas = [item for item in seen if item["type"] == "MODEL_DELTA"]
    assert [item["seq"] for item in deltas] == list(range(deltas[0]["seq"], deltas[0]["seq"] + len(deltas)))
    last = deltas[-1]["seq"]
    replay = db.events_for(run["id"], last)
    assert all(item["seq"] > last for item in replay)
    assert wait_status(client, run["id"], {"completed"})["status"] == "completed"
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
    assert shot.json()["evalResults"][0]["status"] == "pass"

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
