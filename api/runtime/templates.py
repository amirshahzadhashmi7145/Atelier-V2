"""Starter team templates: preset compositions of seed roles a new user can
instantiate in one click, then just add their provider API key and start.

A template is data — it names a set of seed roles (see runtime.roles.SEED_ROLES).
Instantiating one creates an agent per role (wired to the provider/model the user
picks at that moment) and a project whose members are that team. The lead among the
members drives the chat (see runtime.lead.lead_of)."""

from __future__ import annotations

from runtime import roles as rolelib

# Each template lists seed role ids, ordered lead-first so the project's primary
# member is the supervisor that receives the chat.
TEMPLATES = [
    {
        "id": "fullstack-web",
        "name": "Full-stack web app",
        "description": (
            "A Team Lead and QA reviewer supervising a Frontend and a Backend engineer. "
            "Best for web apps with a UI and an API."
        ),
        "roles": ["team-lead", "qa-engineer", "frontend-engineer", "backend-engineer"],
    },
    {
        "id": "frontend-only",
        "name": "Frontend only",
        "description": (
            "A Team Lead reviewing a Frontend engineer. Best for static sites, SPAs, and "
            "UI-focused work."
        ),
        "roles": ["team-lead", "frontend-engineer"],
    },
    {
        "id": "backend-api",
        "name": "Backend / API service",
        "description": (
            "A Team Lead reviewing a Backend engineer. Best for APIs, services, and "
            "server-side logic."
        ),
        "roles": ["team-lead", "backend-engineer"],
    },
]

_BY_ID = {template["id"]: template for template in TEMPLATES}


def _role_summary(role_id: str) -> dict | None:
    role = rolelib.SEED_BY_ID.get(role_id)
    if not role:
        return None
    return {"roleKey": role["id"], "name": role["name"], "kind": role["kind"], "tags": role.get("tags") or []}


def _public(template: dict) -> dict:
    members = [summary for role_id in template["roles"] if (summary := _role_summary(role_id))]
    return {
        "id": template["id"],
        "name": template["name"],
        "description": template["description"],
        "members": members,
    }


def public_list() -> list[dict]:
    return [_public(template) for template in TEMPLATES]


def get(template_id: str) -> dict | None:
    template = _BY_ID.get(template_id)
    return _public(template) if template else None
