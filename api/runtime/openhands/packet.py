"""Task input for an OpenHands run: compiled prompt plus board records."""

from __future__ import annotations

from runtime import board
from runtime.compile import compile_prompt
from store import db

OWN_TOOLS = {"search_data", "load_skill"}


def engine_value(agent: dict | None) -> str:
    value = (agent or {}).get("workerEngine") or "loop"
    return "openhands" if value == "openhands" else "loop"


def compiled_prompt(agent: dict) -> str:
    version = db.get("version", agent.get("activePromptVersionId") or "")
    sections = (version or {}).get("sections") or {}
    model = (agent.get("model") or {}).get("name") or "gpt-4o"
    compiled = compile_prompt(
        sections,
        agent.get("toolIds") or [],
        agent.get("skillIds") or [],
        agent.get("stackIds") or [],
        model=model,
        scope=agent.get("scope"),
        include_tools=False,
    )
    return compiled["compiled"]


def mcp_config(agent: dict) -> dict:
    servers: dict[str, dict] = {}
    catalog = {item["id"]: item for item in db.listing("tool")}
    by_name = {item["name"]: item for item in db.listing("tool")}
    for tool_id in agent.get("toolIds") or []:
        tool = catalog.get(tool_id) or by_name.get(tool_id)
        if not tool or tool.get("kind") != "mcp":
            continue
        if tool.get("name") in OWN_TOOLS or tool.get("id") in OWN_TOOLS:
            continue
        cfg = tool.get("config") or {}
        entry: dict = {}
        if cfg.get("url"):
            entry["url"] = cfg["url"]
        if cfg.get("command"):
            entry["command"] = cfg["command"]
            if cfg.get("args"):
                entry["args"] = cfg["args"]
        if entry:
            servers[tool.get("name") or tool_id] = entry
    return {"mcpServers": servers}


def task_packet(task: dict, agent: dict) -> str:
    lines = [compiled_prompt(agent), "", board.rework_packet(task) or f"# Task\n{task.get('text') or ''}"]
    criteria = task.get("acceptanceCriteria") or []
    if criteria and "Acceptance:" not in "\n".join(lines):
        lines.append("Acceptance: " + "; ".join(str(item) for item in criteria))
    lines.append(
        "Commit your work on this branch. If you are blocked or need a decision, "
        "state the open question; do not ask the user."
    )
    return "\n".join(lines).strip()
