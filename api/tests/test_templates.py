"""Tests for starter team templates: listing presets and instantiating one into a
ready-to-run team + project."""

from __future__ import annotations

from fastapi.testclient import TestClient

from store import db

from test_engine import client, fresh  # noqa: F401


def test_list_templates_exposes_presets_with_members(client: TestClient):
    rows = client.get("/templates").json()
    ids = {row["id"] for row in rows}
    assert {"fullstack-web", "frontend-only", "backend-api"} <= ids
    fullstack = next(row for row in rows if row["id"] == "fullstack-web")
    # Lead-first ordering and the full four-role team.
    assert [m["roleKey"] for m in fullstack["members"]] == [
        "team-lead",
        "qa-engineer",
        "frontend-engineer",
        "backend-engineer",
    ]
    assert fullstack["members"][0]["kind"] == "supervisor"


def test_instantiate_creates_team_and_project(client: TestClient):
    res = client.post("/templates/frontend-only/instantiate", json={"name": "My Site"})
    assert res.status_code == 201
    project = res.json()
    assert project["name"] == "My Site"
    assert project["templateId"] == "frontend-only"

    members = [db.get("agent", mid) for mid in project["members"]]
    assert [a["roleKey"] for a in members] == ["team-lead", "frontend-engineer"]
    # The lead is first so lead_of() picks the Team Lead to drive the chat.
    from runtime import lead as leadlib

    assert leadlib.lead_of(db.get("project", project["id"]))["roleKey"] == "team-lead"
    # The frontend agent carries the role's zones.
    frontend = next(a for a in members if a["roleKey"] == "frontend-engineer")
    assert "src/**" in frontend["zones"]


def test_instantiate_applies_chosen_provider_and_model(client: TestClient):
    res = client.post(
        "/templates/backend-api/instantiate",
        json={"name": "API svc", "provider": "gemini", "model": "gemini-3.1-pro-preview"},
    )
    assert res.status_code == 201
    project = res.json()
    members = [db.get("agent", mid) for mid in project["members"]]
    for agent in members:
        assert agent["model"]["provider"] == "gemini"
        assert agent["model"]["name"] == "gemini-3.1-pro-preview"


def test_instantiate_requires_name(client: TestClient):
    res = client.post("/templates/fullstack-web/instantiate", json={})
    assert res.status_code == 422


def test_instantiate_unknown_template_is_404(client: TestClient):
    assert client.post("/templates/nope/instantiate", json={"name": "x"}).status_code == 404
