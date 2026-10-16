"""Assign a task to a project member: mention, scope, keyword, then classifier."""

from __future__ import annotations

import os
import re

from gateway import openai_gateway
from runtime import lead as leadlib
from store import db

MENTION = re.compile(r"^@([A-Za-z]+)", re.I)
FRONTEND_KW = re.compile(r"\b(react|component|page|css|ui|button|layout|styling|tailwind|frontend)\b", re.I)
BACKEND_KW = re.compile(r"\b(apis?|endpoint|database|auth|jwt|migration|prisma|express|backend|login|signup)\b", re.I)
SPLIT_HINT = re.compile(r"\b(todo app|with login|react ui|node api|and a react|and a node)\b", re.I)

DOES_HINTS = {
    "http apis": ("api", "endpoint", "http", "rest", "route"),
    "databases and migrations": ("database", "prisma", "sqlite", "migration", "sql"),
    "auth backends": ("auth", "jwt", "login", "signup", "password"),
    "background jobs": ("job", "queue", "worker", "cron"),
    "server-side validation": ("validation", "zod", "schema"),
    "user interfaces": ("ui", "page", "component", "button", "layout", "css", "react"),
    "client-side state": ("state", "hook", "redux", "zustand"),
    "styling": ("css", "tailwind", "style", "theme"),
    "calling an existing api": ("fetch", "client", "consume"),
}

NEVER_HINTS = {
    "user interfaces": ("ui", "page", "component", "css", "react", "button"),
    "client-side state": ("zustand", "redux", "usestate"),
    "styling": ("css", "tailwind", "styling"),
    "servers": ("server", "express", "node api"),
    "databases": ("database", "prisma", "sql"),
    "api implementation": ("endpoint", "http api", "http apis", "rest api"),
    "auth backends": ("jwt", "signup", "auth backend"),
    "infrastructure": ("kubernetes", "terraform", "docker compose"),
}


def parse_mention(text: str) -> tuple[str | None, str]:
    match = MENTION.match(text.strip())
    if not match:
        return None, text
    return match.group(1).strip(), text[match.end() :].strip() or text


def _agents(project: dict) -> list[dict]:
    rows = []
    for agent_id in project.get("members") or []:
        agent = db.get("agent", agent_id)
        if agent:
            rows.append(agent)
    return rows


def _kind(agent: dict) -> str:
    blob = f"{agent.get('roleKey') or ''} {agent.get('name') or ''}".lower()
    if "backend" in blob:
        return "backend"
    if "frontend" in blob:
        return "frontend"
    return "other"


def _match_hints(text: str, items: list[str], table: dict[str, tuple[str, ...]]) -> bool:
    low = text.lower()
    for item in items:
        key = item.lower()
        if key in low:
            return True
        for hint in table.get(key, ()):
            if re.search(rf"\b{re.escape(hint)}\b", low):
                return True
    return False


def does_match(agent: dict, text: str) -> bool:
    return _match_hints(text, (agent.get("scope") or {}).get("does") or [], DOES_HINTS)


def never_match(agent: dict, text: str) -> bool:
    return _match_hints(text, (agent.get("scope") or {}).get("neverDoes") or [], NEVER_HINTS)


def _keyword_kind(text: str) -> str | None:
    front = bool(FRONTEND_KW.search(text))
    back = bool(BACKEND_KW.search(text))
    if front and not back:
        return "frontend"
    if back and not front:
        return "backend"
    return None


def _pick(agents: list[dict], kind: str) -> dict | None:
    return next((item for item in agents if _kind(item) == kind), None)


def _assign(task: dict, agent: dict, routed_by: str) -> dict:
    task["assignedAgentId"] = agent["id"]
    task["routedBy"] = routed_by
    task.pop("splitKind", None)
    task.pop("children", None)
    return task


def _split(task: dict, agents: list[dict]) -> dict:
    backend = _pick(agents, "backend")
    frontend = _pick(agents, "frontend")
    if not backend or not frontend:
        chosen = backend or frontend or agents[0]
        return _assign(task, chosen, "rule")
    original = task.get("text") or ""
    task["assignedAgentId"] = ""
    task["routedBy"] = "rule"
    task["splitKind"] = "both"
    task["children"] = [
        {
            "assignedAgentId": backend["id"],
            "text": f"{original}\n\nImplement the HTTP API, database, and auth. List endpoints in complete.summary.endpoints.",
        },
        {
            "assignedAgentId": frontend["id"],
            "text": f"{original}\n\nBuild the UI against api/CONTRACT.md. Do not implement the server.",
        },
    ]
    return task


def _classifier_choice(agents: list[dict], text: str) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        if SPLIT_HINT.search(text) or (FRONTEND_KW.search(text) and BACKEND_KW.search(text)):
            return "both"
        kind = _keyword_kind(text)
        return kind or "frontend"
    names = []
    for agent in agents:
        scope = agent.get("scope") or {}
        names.append(
            f"{agent['id']} name={agent.get('name')} kind={_kind(agent)} does={', '.join(scope.get('does') or [])} never={', '.join(scope.get('neverDoes') or [])}"
        )
    try:
        turn = openai_gateway.complete(
            os.environ.get("GEMINI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini",
            [
                {
                    "role": "user",
                    "content": (
                        "Pick exactly one word: frontend, backend, or both.\n"
                        "both = the work needs an API and a UI.\n"
                        f"Members:\n{chr(10).join(names)}\nMessage: {text}"
                    ),
                }
            ],
            [],
            {},
        )
        word = (turn.get("content") or "both").strip().lower().split()
        found = word[0] if word else "both"
        return found if found in ("frontend", "backend", "both") else "both"
    except Exception:
        return "both"


def route_task(project: dict, task: dict) -> dict:
    mention, stripped = parse_mention(task.get("text") or "")
    agents = _agents(project)
    members = project.get("members") or []
    if not agents:
        if len(members) == 1:
            task["assignedAgentId"] = members[0]
            task["routedBy"] = "user"
            return task
        raise ValueError("routing needs a project member")
    lead = leadlib.lead_of(project)
    if lead and not task.get("parentTaskId") and not task.get("assignedAgentId"):
        if mention:
            task["mention"] = mention
        return _assign(task, lead, "user")
    if mention:
        task["text"] = stripped
        task["mention"] = mention
    if mention:
        needle = mention.lower()
        match = next((item for item in agents if needle in (item.get("name") or "").lower() or needle in (item.get("roleKey") or "").lower() or needle in _kind(item)), None)
        if match:
            return _assign(task, match, "user")
    if len(agents) == 1:
        return _assign(task, agents[0], "user")
    text = task.get("text") or ""
    if SPLIT_HINT.search(text) or (FRONTEND_KW.search(text) and BACKEND_KW.search(text)):
        return _split(task, agents)
    exclusive = []
    for agent in agents:
        others = [item for item in agents if item["id"] != agent["id"]]
        if does_match(agent, text) and others and all(never_match(item, text) for item in others):
            exclusive.append(agent)
    if len(exclusive) == 1:
        return _assign(task, exclusive[0], "rule")
    kind = _keyword_kind(text)
    if kind:
        picked = _pick(agents, kind)
        if picked:
            return _assign(task, picked, "rule")
    choice = _classifier_choice(agents, text)
    if choice == "both":
        return _split(task, agents)
    picked = _pick(agents, choice) or agents[0]
    return _assign(task, picked, "rule")
