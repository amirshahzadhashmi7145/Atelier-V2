"""search_data and load_skill for OpenHands, using the same tool implementations."""

from __future__ import annotations

import json
from pathlib import Path

from runtime import tools
from store import db

TOOLS = {
    "search_data": {
        "name": "search_data",
        "description": "Search the data sources attached to this agent.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "load_skill": {
        "name": "load_skill",
        "description": "Load a skill body into the context.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    "get_lessons": {
        "name": "get_lessons",
        "description": "Load short lessons for this agent's role.",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def skill_ids(agent: dict) -> set[str]:
    names = set(agent.get("skillIds") or [])
    names.update((agent.get("capabilities") or {}).get("skills") or [])
    return names


def owns_skill(agent: dict, skill: dict) -> bool:
    allowed = skill_ids(agent)
    return skill.get("id") in allowed or skill.get("name") in allowed


def invoke(run: dict, name: str, arguments: dict) -> dict:
    agent = db.get("agent", run.get("agentId") or "") or {}
    if name == "search_data":
        result = tools._search(agent, arguments.get("query") or "")
    elif name == "load_skill":
        wanted = arguments.get("name") or ""
        skills = db.listing("skill")
        skill = next((item for item in skills if item.get("name") == wanted or item.get("id") == wanted), None)
        if skill is None or not owns_skill(agent, skill):
            result = {"refused": True, "reason": f"unknown skill {wanted}"}
        else:
            folder = Path(run["folder"]) if run.get("folder") else None
            workspace = db.get("workspace", run.get("id") or "") or {}
            if folder is None and workspace.get("folder"):
                folder = Path(workspace["folder"])
            result = tools._skill(run, folder, wanted)
    elif name == "get_lessons":
        from runtime import lessons

        result = {"output": lessons.for_prompt(agent.get("roleKey") or "")}
    else:
        result = {"refused": True, "reason": f"unknown tool {name}"}
    blob = json.dumps(result, default=str)
    db.append_event(run["id"], "MCP_TOOL_CALLED", {"name": name, "resultBytes": len(blob.encode("utf-8"))})
    return result


def list_tools() -> list[dict]:
    return list(TOOLS.values())
