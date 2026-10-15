import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["GATEWAY_MOCK"] = "1"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["PROJECTS_DIR"] = "/tmp/agent-studio-transcript"

from app.main import app  # noqa: E402
from gateway import openai_gateway  # noqa: E402
from gateway.tool_pairing import assert_chat_tool_pairing  # noqa: E402
from runtime import messages as msglib  # noqa: E402
from store import db  # noqa: E402


@pytest.fixture
def client(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ["PROJECTS_DIR"] = str(tmp_path / "projects")
    db.reset_engine()
    openai_gateway.SCRIPTS.clear()
    openai_gateway.begin()
    with TestClient(app) as test_client:
        yield test_client


def test_run_keeps_tool_results_on_transcript(client: TestClient):
    openai_gateway.SCRIPTS.extend(
        [
            {
                "content": "",
                "tool_calls": [{"id": "r1", "name": "files", "arguments": {"op": "read", "path": "package.json"}}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            {
                "content": "",
                "tool_calls": [{"id": "w1", "name": "files", "arguments": {"op": "write", "path": "src/App.tsx", "content": "export {}"}}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "done",
                        "name": "complete",
                        "arguments": {
                            "summary": {
                                "description": "ok",
                                "filesChanged": ["src/App.tsx"],
                                "dependencies": [],
                                "criteria": [],
                                "assumptions": [],
                                "followUps": [],
                            }
                        },
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
    )
    agent = client.post(
        "/agents",
        json={"name": "FE", "roleKey": "frontend", "toolIds": ["files"], "zones": ["."], "scope": {"does": ["ui"], "neverDoes": [], "zones": ["."]}},
    ).json()
    version = client.post(f"/agents/{agent['id']}/versions", json={"sections": {"role": "R", "goal": "G", "instructions": "I", "constraints": "C", "output": "O"}}).json()
    row = db.get("agent", agent["id"])
    row["activePromptVersionId"] = version["id"]
    db.put("agent", agent["id"], row)
    run = client.post("/runs", json={"agentId": agent["id"], "workspace": {"kind": "scaffold", "template": "local"}, "task": "Build"}).json()
    deadline = time.time() + 8
    while time.time() < deadline:
        status = client.get(f"/runs/{run['id']}").json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    track = db.get("run-track", run["id"]) or {}
    transcript = track.get("transcript") or []
    assert len(transcript) >= 4
    msglib.merge_system_and_transcript("sys", transcript, [{"role": "user", "content": "Build"}], [])
    assert_chat_tool_pairing(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "Build"}, *transcript]
    )
