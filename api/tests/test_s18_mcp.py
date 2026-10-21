"""Studio MCP server for search_data and load_skill, with run-scoped tokens."""

from __future__ import annotations

from fastapi.testclient import TestClient

from runtime.mcp import handler, tokens
from runtime.openhands.client import FakeOpenHands
from runtime.openhands.packet import STUDIO_MCP
from runtime.tools import dispatch
from store import db

from test_engine import client, fresh  # noqa: F401
from test_s17_openhands import _agent, _run, _workspace


def _source(source_id: str, name: str, ref: str) -> dict:
    row = {"id": source_id, "name": name, "ref": ref, "kind": "github_path"}
    db.put("datasource", source_id, row)
    return row


def _skill(skill_id: str, name: str, body: str) -> dict:
    row = {
        "id": skill_id,
        "name": name,
        "description": name,
        "body": body,
        "files": [],
        "version": 1,
        "versions": [],
        "origin": "test",
        "createdAt": db.now(),
    }
    db.put("skill", skill_id, row)
    return row


def _bound_run(client: TestClient, skill_ids=None, source_ids=None) -> tuple[dict, dict, str]:
    sources = source_ids or ["docs-a"]
    for item in sources:
        if not db.get("datasource", item):
            _source(item, "React docs", "https://example.com/react")
    skills = skill_ids or ["react-best-practices"]
    if "react-best-practices" in skills and not db.get("skill", "react-best-practices"):
        _skill("react-best-practices", "react-best-practices", "Use the platform.")
    agent = _agent(client, skillIds=skills, toolIds=["files", "search_data", "load_skill"])
    agent["dataSourceIds"] = sources
    agent["skillIds"] = skills
    db.put("agent", agent["id"], agent)
    project, task = _workspace(client, agent)
    run = {
        "id": db.nid("run"),
        "agentId": agent["id"],
        "projectId": project["id"],
        "taskId": task["id"],
        "status": "running",
        "folder": project["folderPath"],
    }
    db.put("run", run["id"], run)
    db.put("workspace", run["id"], {"folder": project["folderPath"]})
    token = tokens.issue(run["id"])
    return agent, run, token


def _mcp(client: TestClient, token: str | None, method: str, params: dict | None = None, req_id: int = 1):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers=headers)


def test_search_data_matches_direct_tool(client: TestClient):
    _agent_row, run, token = _bound_run(client, source_ids=["docs-a"])
    direct = dispatch(run, "search_data", {"query": "react"}, lambda: False)
    via = handler.invoke(run, "search_data", {"query": "react"})
    assert via == direct
    posted = _mcp(client, token, "tools/call", {"name": "search_data", "arguments": {"query": "react"}})
    assert posted.status_code == 200, posted.text
    assert posted.json()["result"]["structuredContent"] == direct


def test_load_skill_matches_direct_tool(client: TestClient):
    _skill("skill-match", "match-skill", "Use the platform.")
    _agent_row, run, token = _bound_run(client, skill_ids=["skill-match"])
    direct = dispatch(run, "load_skill", {"name": "match-skill"}, lambda: False)
    copy = {**run, "id": db.nid("run")}
    db.put("run", copy["id"], copy)
    db.put("workspace", copy["id"], {"folder": run["folder"]})
    via = handler.invoke(copy, "load_skill", {"name": "match-skill"})
    assert via.get("output") == direct.get("output")
    posted = _mcp(client, token, "tools/call", {"name": "load_skill", "arguments": {"name": "match-skill"}})
    assert posted.status_code == 200
    body = posted.json()["result"]["structuredContent"]
    assert body.get("alreadyLoaded") or "platform" in (body.get("output") or "")


def test_agent_only_sees_own_sources_and_skills(client: TestClient):
    _source("docs-a", "React docs", "https://example.com/react")
    _source("docs-b", "Hidden docs", "https://example.com/hidden")
    _skill("skill-own", "own-skill", "visible body")
    _skill("skill-other", "other-skill", "secret other body")
    _agent_row, run, token = _bound_run(client, skill_ids=["skill-own"], source_ids=["docs-a"])
    found = handler.invoke(run, "search_data", {"query": "react"})
    hidden = handler.invoke(run, "search_data", {"query": "hidden"})
    assert found.get("output") == ["React docs"]
    assert hidden.get("output") == []
    own = handler.invoke(run, "load_skill", {"name": "own-skill"})
    other = handler.invoke(run, "load_skill", {"name": "other-skill"})
    assert "visible body" in (own.get("output") or "")
    assert other.get("refused") is True
    posted = _mcp(client, token, "tools/call", {"name": "load_skill", "arguments": {"name": "other-skill"}})
    assert posted.json()["result"]["isError"] is True


def test_missing_wrong_and_expired_tokens_are_refused(client: TestClient):
    _agent_row, run, token = _bound_run(client)
    missing = _mcp(client, None, "tools/list")
    assert missing.status_code == 401
    wrong = _mcp(client, "atk_notavalidtokenvalue", "tools/list")
    assert wrong.status_code == 401
    row = db.get("mcp-token", run["id"])
    row["expiresAt"] = 0
    db.put("mcp-token", run["id"], row)
    expired = _mcp(client, token, "tools/list")
    assert expired.status_code == 401


def test_token_stops_after_run_ends(client: TestClient):
    agent = _agent(client)
    project, task = _workspace(client, agent)
    fake = FakeOpenHands(files={"src/App.tsx": "export default function App() { return <h1>Hi</h1> }\n"})
    result = _run(project, task, fake)
    assert result["status"] == "completed"
    env = ((fake.last_spec.mcp or {}).get(STUDIO_MCP) or {}).get("env") or {}
    token = env.get("ATELIER_MCP_TOKEN")
    assert token
    posted = _mcp(client, token, "tools/list")
    assert posted.status_code == 401
    assert db.get("mcp-token", result["runId"])["revoked"] is True


def test_mcp_calls_are_recorded_without_secrets(client: TestClient):
    secret_body = "sk" + "-not-a-real-secret-XXXX"
    _skill("skill-own", "own-skill", secret_body)
    _agent_row, run, token = _bound_run(client, skill_ids=["skill-own"], source_ids=["docs-a"])
    _mcp(client, token, "tools/call", {"name": "load_skill", "arguments": {"name": "own-skill"}})
    events = [item for item in db.listing("event") if item.get("runId") == run["id"] and item.get("type") == "MCP_TOOL_CALLED"]
    assert events
    payload = events[-1].get("payload") or {}
    assert payload.get("name") == "load_skill"
    assert isinstance(payload.get("resultBytes"), int) and payload["resultBytes"] > 0
    blob = str(payload)
    assert secret_body not in blob
    assert "visible" not in blob


def test_openhands_run_receives_studio_mcp_and_agent_servers(client: TestClient):
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
    assert STUDIO_MCP in servers
    assert servers[STUDIO_MCP]["args"] == ["-m", "runtime.mcp.stdio"]
    assert "ATELIER_MCP_TOKEN" in (servers[STUDIO_MCP].get("env") or {})
    assert "search_data" not in servers
    assert "load_skill" not in servers
    command = " ".join([servers[STUDIO_MCP]["command"], *servers[STUDIO_MCP]["args"]])
    assert "atk_" not in command
