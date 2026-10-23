"""Task input for an OpenHands run: compiled prompt plus board records."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from runtime import board, lessons, notes
from runtime.compile import compile_prompt
from store import db

OWN_TOOLS = {"search_data", "load_skill", "get_lessons"}
API_ROOT = Path(__file__).resolve().parents[2]
STUDIO_MCP = "atelier"


def engine_value(agent: dict | None) -> str:
    from runtime import roles as rolelib

    if rolelib.is_supervisor(agent):
        return "loop"
    return "openhands"


def compiled_prompt(agent: dict) -> str:
    version = db.get("version", agent.get("activePromptVersionId") or "")
    sections = (version or {}).get("sections") or {}
    model = (agent.get("model") or {}).get("name") or "gpt-4o"
    from runtime import roles as rolelib

    compiled = compile_prompt(
        sections,
        agent.get("toolIds") or [],
        agent.get("skillIds") or [],
        agent.get("stackIds") or [],
        model=model,
        scope=agent.get("scope"),
        include_tools=False,
        worker=not rolelib.is_supervisor(agent),
    )
    return compiled["compiled"]


def studio_mcp_server(token: str) -> dict:
    env = {
        "ATELIER_MCP_TOKEN": token,
        "PYTHONPATH": str(API_ROOT),
    }
    for key in ("DATABASE_URL", "PROJECTS_DIR"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return {
        "command": sys.executable,
        "args": ["-m", "runtime.mcp.stdio"],
        "env": env,
    }


def mcp_config(agent: dict, token: str | None = None) -> dict:
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
    if token:
        servers[STUDIO_MCP] = studio_mcp_server(token)
    return servers


def task_packet(task: dict, agent: dict, project: dict | None = None, notes_text: str | None = None) -> str:
    lines = [compiled_prompt(agent), "", board.rework_packet(task) or f"# Task\n{task.get('text') or ''}"]
    criteria = task.get("acceptanceCriteria") or []
    if criteria and "Acceptance:" not in "\n".join(lines):
        lines.append("Acceptance: " + "; ".join(str(item) for item in criteria))
    block = notes_text if notes_text is not None else (notes.for_prompt(project) if project else "")
    if block:
        lines.append(block)
    taught = lessons.for_prompt(agent.get("roleKey") or "")
    if taught:
        lines.append(taught)
    lines.append("Do not search the filesystem for skills or scan unrelated git history.")
    allowed = _allowed_packages(agent)
    if allowed:
        lines.append(
            "New npm packages must come from this allow-list (wildcards included): "
            + ", ".join(allowed)
            + ". The platform enforces this list; it is not a file in the workspace, so do not search for or try to edit it."
        )
    if _needs_preview(agent):
        lines.append(
            "Verify your work by running the tests and the production build. Do not start a dev server "
            "or open a browser; a preview is served automatically after the task completes."
        )
    else:
        lines.append("Run the tests for the code you changed. Do not start a dev server or open a browser.")
    folder = Path(project["folderPath"]) if project and project.get("folderPath") else None
    if folder and (folder / "package.json").is_file():
        lines.append(
            "A project scaffold with dependencies already exists in the workspace. Read package.json and "
            "build on it; do not run a create command or reinstall from scratch."
        )
    lines.append(
        "Commit your work on this branch. If you are blocked or need a decision, state the open question; do not ask "
        "the user. Do not edit the project notes file."
    )
    return "\n".join(lines).strip()


def _allowed_packages(agent: dict) -> list[str]:
    stacks = {item["id"]: item for item in db.listing("stack")}
    names: list[str] = []
    for stack_id in agent.get("stackIds") or []:
        for name in (stacks.get(stack_id) or {}).get("packageAllowList") or []:
            if name not in names:
                names.append(name)
    return names


def _needs_preview(agent: dict) -> bool:
    blob = " ".join(str(item) for item in ((agent.get("scope") or {}).get("zones") or agent.get("zones") or [])).lower()
    return any(token in blob for token in ("src/", "src/**", "app/", "public/", "index.html", ".tsx", ".jsx"))
