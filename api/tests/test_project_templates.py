"""Tests for pre-built PROJECT templates (HR system, CRM, …): listing them, building
their full-stack files, starting a new project from one (copy-on-select with its own
version history), and that the template itself is never mutated."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from runtime import project_templates
from store import db

from test_engine import client, fresh  # noqa: F401


def test_lists_at_least_ten_templates_with_fields(client: TestClient):
    rows = client.get("/project-templates").json()
    assert len(rows) >= 10
    hr = next(row for row in rows if row["id"] == "hr-system")
    assert hr["entity"] == "Employee"
    assert any(f["name"] == "salary" and f["kind"] == "number" for f in hr["fields"])
    assert hr["teamTemplateId"] in {"fullstack-web", "frontend-only", "backend-api"}


def test_every_template_builds_a_coherent_fullstack_app(tmp_path: Path):
    for domain in project_templates.DOMAINS:
        folder = tmp_path / domain["id"]
        project_templates.build(domain["id"], folder)
        # Frontend
        pkg = json.loads((folder / "package.json").read_text())
        assert "vite" in pkg["devDependencies"]
        assert (folder / "src" / "App.tsx").is_file()
        assert (folder / "src" / "fields.ts").read_text().count("SEED") >= 1
        # Backend
        server_pkg = json.loads((folder / "server" / "package.json").read_text())
        assert "express" in server_pkg["dependencies"]
        schema = (folder / "server" / "prisma" / "schema.prisma").read_text()
        assert f"model {domain['entity']}" in schema
        assert (folder / "server" / "src" / "index.ts").read_text().count("app.") >= 3


def test_build_is_immutable_two_copies_are_independent(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    project_templates.build("crm", a)
    project_templates.build("crm", b)
    # Editing one copy must not touch the other (the template is a generator, not a
    # shared mutable tree).
    (a / "src" / "App.tsx").write_text("// changed\n")
    assert (b / "src" / "App.tsx").read_text() != "// changed\n"
    assert "CRM" in (b / "README.md").read_text()


def test_use_creates_project_with_team_and_first_version(client: TestClient):
    res = client.post("/project-templates/hr-system/use", json={"name": "People App"})
    assert res.status_code == 201
    project = res.json()
    assert project["name"] == "People App"
    assert project["sourceTemplateId"] == "hr-system"

    # A recommended team was created and attached.
    members = [db.get("agent", mid) for mid in project["members"]]
    assert any(a["roleKey"] == "team-lead" for a in members)
    assert any(a["roleKey"] in ("frontend-engineer", "backend-engineer") for a in members)

    # The template files were copied into the new project's own folder.
    folder = Path(db.get("project", project["id"])["folderPath"])
    assert (folder / "server" / "prisma" / "schema.prisma").is_file()

    # It has a first version (the template import commit).
    versions = client.get(f"/projects/{project['id']}/versions").json()["versions"]
    assert len(versions) >= 1
    assert versions[-1]["version"] == 1
    assert "template" in versions[0]["message"].lower()


def test_use_defaults_name_to_template_name(client: TestClient):
    project = client.post("/project-templates/crm/use", json={}).json()
    assert project["name"] == "CRM"


def test_use_unknown_template_is_404(client: TestClient):
    assert client.post("/project-templates/nope/use", json={"name": "x"}).status_code == 404


def test_use_applies_chosen_provider_to_team(client: TestClient):
    project = client.post(
        "/project-templates/task-tracker/use",
        json={"name": "Board", "provider": "gemini", "model": "gemini-3.1-pro-preview"},
    ).json()
    members = [db.get("agent", mid) for mid in project["members"]]
    assert all(a["model"]["provider"] == "gemini" for a in members)
