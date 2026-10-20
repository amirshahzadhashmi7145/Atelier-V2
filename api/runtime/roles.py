"""Role documents: workers and supervisors are data, not code paths."""

from __future__ import annotations

from hashlib import sha1

from store import db

SEED_ROLES = [
    {
        "id": "frontend-engineer",
        "name": "Frontend Engineer",
        "kind": "worker",
        "reportsTo": "team-lead",
        "layer": 0,
        "zones": [
            "src/**",
            "app/**",
            "public/**",
            "index.html",
            "vite.config.*",
            "package.json",
            "tsconfig*.json",
            "tailwind.config.*",
            "postcss.config.*",
        ],
        "tags": ["frontend"],
        "colour": "#2563eb",
        "contractFile": None,
    },
    {
        "id": "backend-engineer",
        "name": "Backend Engineer",
        "kind": "worker",
        "reportsTo": "team-lead",
        "layer": 0,
        "zones": ["api/**", "server/**", "prisma/**", "db/**", "package.json", "tsconfig*.json", ".env.example"],
        "tags": ["backend"],
        "colour": "#d97706",
        "contractFile": "api/CONTRACT.md",
    },
    {
        "id": "team-lead",
        "name": "Team Lead",
        "kind": "supervisor",
        "reportsTo": "qa-engineer",
        "layer": 1,
        "zones": [],
        "tags": ["supervisor", "review", "planning"],
        "colour": "#7c3aed",
        "contractFile": None,
    },
    {
        "id": "qa-engineer",
        "name": "QA Engineer",
        "kind": "supervisor",
        "reportsTo": None,
        "layer": 2,
        "zones": [],
        "tags": ["supervisor", "review"],
        "colour": "#0f766e",
        "contractFile": None,
    },
]

UTILITY_TAGS = ["review", "planning", "cheap", "fast"]


def sync_roles() -> None:
    for role in SEED_ROLES:
        if db.get("role", role["id"]) is None:
            db.put("role", role["id"], dict(role))
    if db.get("meta", "seed-parent-link"):
        return
    for role in SEED_ROLES:
        existing = db.get("role", role["id"])
        if existing and not existing.get("reportsTo") and role.get("reportsTo"):
            layer = existing.get("layer") if existing.get("layer") is not None else role["layer"]
            db.put("role", role["id"], {**existing, "reportsTo": role["reportsTo"], "layer": layer})
    db.put("meta", "seed-parent-link", {"applied": True})


def normalize(body: dict, existing: dict | None = None) -> dict:
    current = dict(existing or {})
    role_id = (body.get("id") or current.get("id") or _slug(body.get("name") or "")).strip()
    if not role_id:
        raise ValueError("id or name is required")
    kind = (body.get("kind") or current.get("kind") or "worker").strip().lower()
    if kind not in ("worker", "supervisor"):
        raise ValueError("kind must be worker or supervisor")
    layer = body.get("layer") if "layer" in body else current.get("layer")
    try:
        layer = int(layer if layer is not None else (1 if kind == "supervisor" else 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("layer must be an integer") from exc
    reports = body.get("reportsTo") if "reportsTo" in body else current.get("reportsTo")
    if reports == "":
        reports = None
    colour = body.get("colour") if "colour" in body else current.get("colour")
    contract = body.get("contractFile") if "contractFile" in body else current.get("contractFile")
    if contract == "":
        contract = None
    return {
        "id": role_id,
        "name": (body.get("name") or current.get("name") or role_id).strip(),
        "kind": kind,
        "reportsTo": reports,
        "layer": layer,
        "zones": list(body.get("zones") if "zones" in body else current.get("zones") or []),
        "tags": list(body.get("tags") if "tags" in body else current.get("tags") or []),
        "colour": colour or None,
        "contractFile": contract,
    }


def _slug(name: str) -> str:
    chars = []
    for char in name.strip().lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-")


def of(agent: dict | None) -> dict | None:
    if not agent:
        return None
    key = agent.get("roleKey") or ""
    if not key:
        return None
    return db.get("role", key)


def is_supervisor(agent: dict | None) -> bool:
    if not agent:
        return False
    role = of(agent)
    if role and role.get("kind") == "supervisor":
        return True
    tags = (agent.get("capabilities") or {}).get("tags") or []
    return "supervisor" in tags


def colour_of(agent: dict | None) -> str:
    role = of(agent)
    if role and role.get("colour"):
        return role["colour"]
    if not agent:
        return "#64748b"
    digest = sha1((agent.get("id") or agent.get("roleKey") or "").encode()).hexdigest()
    return f"#{digest[:6]}"


def contract_file_of(agent: dict | None) -> str | None:
    role = of(agent)
    path = (role or {}).get("contractFile") if role else None
    return path or None


def tags_catalog() -> list[str]:
    seen: list[str] = []
    for role in db.listing("role"):
        for tag in role.get("tags") or []:
            if tag and tag not in seen:
                seen.append(tag)
    for tag in UTILITY_TAGS:
        if tag not in seen:
            seen.append(tag)
    return seen


def supervisor_chain(agent: dict | None) -> list[dict]:
    """Supervisor roles above this agent, walking reportsTo, ordered by layer."""
    role = of(agent)
    chain: list[dict] = []
    seen: set[str] = set()
    current = (role or {}).get("reportsTo")
    while current and current not in seen:
        seen.add(current)
        nxt = db.get("role", current)
        if nxt is None:
            break
        if nxt.get("kind") == "supervisor":
            chain.append(nxt)
        current = nxt.get("reportsTo")
    chain.sort(key=lambda item: (item.get("layer") or 0, item.get("id") or ""))
    return chain


def member_for_role(project: dict | None, role_id: str) -> dict | None:
    if not project or not role_id:
        return None
    for agent_id in project.get("members") or []:
        agent = db.get("agent", agent_id)
        if agent and agent.get("roleKey") == role_id:
            return agent
    return None


def first_reviewer(project: dict | None, worker: dict | None) -> dict | None:
    for role in supervisor_chain(worker):
        member = member_for_role(project, role["id"])
        if member:
            return member
    return None


def next_reviewer(project: dict | None, worker: dict | None, after: dict | None) -> dict | None:
    chain = supervisor_chain(worker)
    after_id = (of(after) or {}).get("id") if after else None
    started = after_id is None
    for role in chain:
        if not started:
            if role.get("id") == after_id:
                started = True
            continue
        member = member_for_role(project, role["id"])
        if member:
            return member
    return None
