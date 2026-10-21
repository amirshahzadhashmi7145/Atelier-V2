"""One place that turns catalog names into provider-safe function names and back."""

from __future__ import annotations

import re

from store import db

SAFE = re.compile(r"[^A-Za-z0-9_-]")

CONTROL = ["load_skill", "complete", "raise_clarification", "escalate"]
SUPERVISOR = ["create_task", "record_review"]
HANDLERS = frozenset(
    {
        "files",
        "shell",
        "package_install",
        "build_test",
        "headless_browser",
        "preview_deploy",
        "search_data",
        "load_skill",
        "get_lessons",
        "complete",
        "raise_clarification",
        "escalate",
        "create_task",
        "record_review",
    }
)


def offered_name(name: str) -> str:
    return SAFE.sub("_", (name or "").strip())


def resolve_offered(offered: str, names: set[str]) -> str:
    raw = (offered or "").strip()
    if raw in names:
        return raw
    mapping = {offered_name(item): item for item in names}
    return mapping.get(raw, raw)


def _catalog() -> tuple[dict, dict]:
    rows = db.listing("tool")
    return {item["id"]: item for item in rows}, {item["name"]: item for item in rows}


def canonical_name(raw: str) -> str:
    by_id, by_name = _catalog()
    tool = by_id.get(raw) or by_name.get(raw)
    if tool:
        return tool.get("name") or raw
    return raw


def allowed_canonical(agent: dict) -> set[str]:
    ids = set(agent.get("toolIds") or []) | set(CONTROL)
    from runtime import lead as leadlib

    if leadlib.is_lead(agent):
        ids |= set(SUPERVISOR)
    names: set[str] = set()
    for item_id in ids:
        name = canonical_name(item_id)
        if name in HANDLERS:
            names.add(name)
    return names


def resolve_call(offered: str, agent: dict) -> str:
    return resolve_offered(offered, allowed_canonical(agent))


def unmapped_offered(agent: dict) -> list[str]:
    bad = []
    for item in openai_tool_defs(agent):
        name = item["function"]["name"]
        resolved = resolve_call(name, agent)
        if resolved not in HANDLERS:
            bad.append(name)
    return bad


def openai_tool_defs(agent: dict) -> list[dict]:
    catalog = {item["name"]: item for item in db.listing("tool")}
    result = []
    for name in sorted(allowed_canonical(agent)):
        tool = catalog.get(name)
        if not tool:
            continue
        result.append(
            {
                "type": "function",
                "function": {
                    "name": offered_name(name),
                    "description": tool["description"],
                    "parameters": tool["schema"],
                },
            }
        )
    return result
