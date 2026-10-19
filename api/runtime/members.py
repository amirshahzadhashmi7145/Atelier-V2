"""Project membership, zone overlap, and agent colour."""

from __future__ import annotations

from fnmatch import fnmatch

from runtime import roles as rolelib
from store import db

SHARED_ZONES = ("package.json", "tsconfig.json", "tsconfig*.json")


def color_for(agent: dict | None) -> str:
    return rolelib.colour_of(agent)


def zones_of(agent: dict | None) -> list[str]:
    if not agent:
        return []
    scope = agent.get("scope") or {}
    return list(scope.get("zones") or agent.get("zones") or [])


def is_shared_zone(pattern: str) -> bool:
    pure = pattern.replace("\\", "/").lstrip("/")
    return any(pure == item or fnmatch(pure, item) or fnmatch(item.replace("*", "x"), pure) for item in SHARED_ZONES) or pure in SHARED_ZONES


def is_shared_path(path: str) -> bool:
    pure = path.replace("\\", "/").lstrip("/")
    name = pure.split("/")[-1]
    return any(fnmatch(name, item) or fnmatch(pure, item) for item in SHARED_ZONES)


def _sample(pattern: str) -> str:
    return pattern.replace("**", "item").replace("*", "x").lstrip("/")


def zones_conflict(left: str, right: str) -> bool:
    if is_shared_zone(left) or is_shared_zone(right):
        return False
    a = left.replace("\\", "/").lstrip("/")
    b = right.replace("\\", "/").lstrip("/")
    if a == b:
        return True
    return fnmatch(_sample(a), b) or fnmatch(_sample(b), a) or fnmatch(a.rstrip("/*"), b) or fnmatch(b.rstrip("/*"), a)


def overlapping_zones(first: list[str], second: list[str]) -> list[str]:
    found: list[str] = []
    for left in first:
        for right in second:
            if zones_conflict(left, right):
                pair = f"{left} ∩ {right}"
                if pair not in found:
                    found.append(pair)
    return found


def member_overlap(project: dict, incoming: dict) -> list[str]:
    incoming_zones = zones_of(incoming)
    found: list[str] = []
    for agent_id in project.get("members") or []:
        if agent_id == incoming.get("id"):
            continue
        other = db.get("agent", agent_id) or {}
        found.extend(overlapping_zones(incoming_zones, zones_of(other)))
    return found


def other_member_busy(run: dict) -> bool:
    project_id = run.get("projectId")
    if not project_id:
        return False
    from runtime import project_runs

    live = project_runs.working(project_id)
    if live is None:
        return False
    return live.get("agentId") != run.get("agentId") and live.get("id") != run.get("id")


def last_task_for(project_id: str, agent_id: str) -> tuple[str | None, str | None]:
    rows = [
        item
        for item in db.listing("task")
        if item.get("projectId") == project_id and item.get("assignedAgentId") == agent_id and item.get("text")
    ]
    if not rows:
        return None, None
    rows.sort(key=lambda item: item.get("id") or "")
    text = (rows[-1].get("text") or "").strip()
    return (text[:120] if text else None), rows[-1].get("id")


def member_details(project: dict) -> list[dict]:
    details = []
    members = [db.get("agent", item) for item in project.get("members") or []]
    members = [item for item in members if item]
    for agent in members:
        others = [zones_of(item) for item in members if item["id"] != agent["id"]]
        overlap: list[str] = []
        for other in others:
            overlap.extend(overlapping_zones(zones_of(agent), other))
        last_text, last_id = last_task_for(project["id"], agent["id"])
        details.append(
            {
                "agentId": agent["id"],
                "name": agent.get("name") or agent["id"],
                "roleKey": agent.get("roleKey") or "",
                "color": color_for(agent),
                "zones": zones_of(agent),
                "overlapZones": overlap,
                "lastTask": last_text,
                "lastTaskId": last_id,
            }
        )
    return details


def stamp(agent: dict | None) -> dict:
    if not agent:
        return {}
    return {"agentId": agent["id"], "agentName": agent.get("name") or agent["id"], "agentColor": color_for(agent)}
