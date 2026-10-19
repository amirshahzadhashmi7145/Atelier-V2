"""Assign a task to a project member from scope, tags, and role data."""

from __future__ import annotations

import os
import re

from gateway import openai_gateway
from runtime import lead as leadlib
from runtime import roles as rolelib
from store import db

MENTION = re.compile(r"^@([A-Za-z]+)", re.I)

DOES_HINTS = {
    "http apis": ("api", "endpoint", "http", "rest", "route"),
    "databases and migrations": ("database", "prisma", "sqlite", "migration", "sql"),
    "auth work": ("auth", "jwt", "login", "signup", "password"),
    "background jobs": ("job", "queue", "worker", "cron"),
    "server-side validation": ("validation", "zod", "schema"),
    "user interfaces": ("ui", "page", "component", "button", "layout", "css", "react", "app", "form", "screen"),
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
    "auth work": ("jwt", "signup"),
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


def _workers(agents: list[dict]) -> list[dict]:
    return [item for item in agents if not leadlib.is_lead(item)]


def _hints_for(item: str, table: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    key = item.lower()
    if key in table:
        return table[key]
    if "auth" in key:
        return table.get("auth work", ())
    return ()


def _match_hints(text: str, items: list[str], table: dict[str, tuple[str, ...]]) -> bool:
    low = text.lower()
    for item in items:
        key = item.lower()
        if key in low:
            return True
        for hint in _hints_for(item, table):
            if re.search(rf"\b{re.escape(hint)}\b", low):
                return True
    return False


def does_match(agent: dict, text: str) -> bool:
    return _match_hints(text, (agent.get("scope") or {}).get("does") or [], DOES_HINTS)


def never_match(agent: dict, text: str) -> bool:
    return _match_hints(text, (agent.get("scope") or {}).get("neverDoes") or [], NEVER_HINTS)


def _tag_match(agent: dict, text: str) -> bool:
    role = rolelib.of(agent)
    tags = list((role or {}).get("tags") or [])
    tags.extend((agent.get("capabilities") or {}).get("tags") or [])
    low = text.lower()
    skip = {"supervisor", "review", "planning", "cheap", "fast"}
    for tag in tags:
        token = str(tag).strip().lower()
        if not token or token in skip:
            continue
        if re.search(rf"\b{re.escape(token)}\b", low):
            return True
    return False


def _score(agent: dict, text: str) -> int:
    if never_match(agent, text):
        return -1
    score = 0
    if does_match(agent, text):
        score += 2
    if _tag_match(agent, text):
        score += 1
    return score


def _assign(task: dict, agent: dict, routed_by: str) -> dict:
    task["assignedAgentId"] = agent["id"]
    task["routedBy"] = routed_by
    task.pop("splitKind", None)
    task.pop("children", None)
    return task


def _contract_rank(agent: dict) -> int:
    return 0 if rolelib.contract_file_of(agent) else 1


def _split(task: dict, workers: list[dict]) -> dict:
    ordered = sorted(workers, key=lambda item: (_contract_rank(item), item.get("name") or item["id"]))
    original = task.get("text") or ""
    task["assignedAgentId"] = ""
    task["routedBy"] = "rule"
    task["splitKind"] = "both"
    children = []
    for agent in ordered:
        scope = agent.get("scope") or {}
        does = ", ".join(scope.get("does") or []) or "the assigned work"
        never = ", ".join(scope.get("neverDoes") or []) or "nothing extra"
        extra = ""
        contract = rolelib.contract_file_of(agent)
        if contract:
            extra = f" Produce {contract}."
        children.append(
            {
                "assignedAgentId": agent["id"],
                "text": f"{original}\n\nDo: {does}. Never: {never}.{extra}",
            }
        )
    task["children"] = children
    return task


def _classifier_choice(agents: list[dict], text: str) -> str:
    """Return 'split', an agent id, or 'supervisor'."""
    workers = _workers(agents) or agents
    scored = [( _score(item, text), item) for item in workers]
    positive = [item for score, item in scored if score > 0]
    if os.environ.get("GATEWAY_MOCK") == "1":
        if len(positive) >= 2:
            return "split"
        if len(positive) == 1:
            return positive[0]["id"]
        return "supervisor"
    names = []
    for agent in agents:
        scope = agent.get("scope") or {}
        role = rolelib.of(agent)
        names.append(
            f"{agent['id']} name={agent.get('name')} kind={(role or {}).get('kind') or 'worker'} "
            f"tags={', '.join((role or {}).get('tags') or [])} "
            f"does={', '.join(scope.get('does') or [])} never={', '.join(scope.get('neverDoes') or [])}"
        )
    try:
        turn = openai_gateway.complete(
            os.environ.get("GEMINI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini",
            [
                {
                    "role": "user",
                    "content": (
                        "Pick one member id, or the word split if more than one worker should share the work, "
                        "or the word supervisor if a supervisor should decide.\n"
                        f"Members:\n{chr(10).join(names)}\nMessage: {text}"
                    ),
                }
            ],
            [],
            {},
        )
        word = (turn.get("content") or "supervisor").strip().split()
        found = word[0] if word else "supervisor"
        ids = {item["id"] for item in agents}
        if found in ids or found in ("split", "supervisor"):
            return found
        return "supervisor"
    except Exception:
        return "supervisor"


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
        needle = mention.lower()
        match = next(
            (
                item
                for item in agents
                if needle in (item.get("name") or "").lower() or needle in (item.get("roleKey") or "").lower()
            ),
            None,
        )
        if match:
            return _assign(task, match, "user")
    if len(agents) == 1:
        return _assign(task, agents[0], "user")
    text = task.get("text") or ""
    workers = _workers(agents)
    pool = workers or agents
    exclusive = []
    for agent in pool:
        others = [item for item in pool if item["id"] != agent["id"]]
        if _score(agent, text) > 0 and others and all(never_match(item, text) or _score(item, text) <= 0 for item in others):
            exclusive.append(agent)
    if len(exclusive) == 1:
        return _assign(task, exclusive[0], "rule")
    positive = [item for item in pool if _score(item, text) > 0]
    if len(positive) >= 2:
        return _split(task, positive)
    choice = _classifier_choice(agents, text)
    if choice == "split" and len(pool) >= 2:
        return _split(task, pool)
    if choice == "supervisor":
        if lead:
            return _assign(task, lead, "agent")
        if len(positive) == 1:
            return _assign(task, positive[0], "rule")
        return _assign(task, pool[0], "rule")
    picked = next((item for item in agents if item["id"] == choice), None)
    if picked:
        return _assign(task, picked, "rule")
    if len(positive) == 1:
        return _assign(task, positive[0], "rule")
    return _assign(task, pool[0], "rule")
