"""Tests for editing a project's GitHub repo/token after creation and for the
open-folder endpoint (both added for the project settings panel)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import routes
from store import db

from test_engine import client, fresh  # noqa: F401
from test_s17_openhands import _agent  # noqa: F401


def test_patch_sets_repo_and_token_without_returning_token(client: TestClient):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "GH", "agentId": agent["id"]}).json()
    assert project["repoUrl"] is None
    assert project["tokenRef"] is None

    res = client.patch(
        f"/projects/{project['id']}",
        json={"repoUrl": "https://github.com/owner/repo", "githubToken": "tok-round-trip-value"},
    )
    assert res.status_code == 200
    patched = res.json()
    assert patched["repoUrl"] == "https://github.com/owner/repo"
    assert patched["tokenRef"] == f"file:{project['id']}"
    # The raw token must never be echoed back to the client.
    assert "tok-round-trip-value" not in res.text
    assert "githubToken" not in patched

    # It is persisted by reference in the per-project secrets file, 0600.
    secret = db.projects_dir() / ".secrets" / project["id"]
    assert secret.read_text() == "tok-round-trip-value"
    assert (secret.stat().st_mode & 0o777) == 0o600


def test_patch_repo_only_keeps_existing_token(client: TestClient):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "GH2", "agentId": agent["id"]}).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-keep-me-value"})

    patched = client.patch(f"/projects/{project['id']}", json={"repoUrl": "https://github.com/o/r2"}).json()
    assert patched["repoUrl"] == "https://github.com/o/r2"
    # No new token supplied -> the stored file reference is preserved.
    assert patched["tokenRef"] == f"file:{project['id']}"
    secret = db.projects_dir() / ".secrets" / project["id"]
    assert secret.read_text() == "tok-keep-me-value"


def test_patch_can_clear_repo_url(client: TestClient):
    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "GH3", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    assert project["repoUrl"] == "https://github.com/o/r"
    patched = client.patch(f"/projects/{project['id']}", json={"repoUrl": ""}).json()
    assert patched["repoUrl"] is None


def test_open_folder_launches_opener_in_local_mode(client: TestClient, monkeypatch):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "Open", "agentId": agent["id"]}).json()

    calls: list[list[str]] = []
    monkeypatch.setattr(routes.bridge, "local_mode", lambda: True)
    monkeypatch.setattr(routes.subprocess, "Popen", lambda argv, **kw: calls.append(argv))

    res = client.post(f"/projects/{project['id']}/open-folder")
    assert res.status_code == 200
    assert res.json()["folderPath"] == project["folderPath"]
    assert len(calls) == 1
    assert calls[0][-1] == project["folderPath"]


def test_open_folder_rejected_when_not_local(client: TestClient, monkeypatch):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "OpenRemote", "agentId": agent["id"]}).json()
    launched = []
    monkeypatch.setattr(routes.bridge, "local_mode", lambda: False)
    monkeypatch.setattr(routes.subprocess, "Popen", lambda argv, **kw: launched.append(argv))

    res = client.post(f"/projects/{project['id']}/open-folder")
    assert res.status_code == 409
    assert launched == []


def test_open_folder_missing_project_is_404(client: TestClient):
    assert client.post("/projects/prj_does_not_exist/open-folder").status_code == 404


def test_push_requires_repo_and_token(client: TestClient):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "NoRepo", "agentId": agent["id"]}).json()
    res = client.post(f"/projects/{project['id']}/push")
    assert res.status_code == 422
    assert "settings" in res.json()["message"].lower()


def test_push_to_default_branch(client: TestClient, monkeypatch):
    from runtime import github

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "Push", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-push-value"})

    git_calls: list[list[str]] = []
    monkeypatch.setattr(github, "default_branch", lambda url, token: "main")
    monkeypatch.setattr(github, "run_git", lambda folder, args: git_calls.append(args) or "")
    monkeypatch.setattr(github, "open_pull_request", lambda *a, **k: None)

    res = client.post(f"/projects/{project['id']}/push")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["branch"] == "main"
    assert data["prUrl"] is None
    # It pushed HEAD to the default branch and the token is never echoed back.
    assert any(args[:1] == ["push"] and args[-1] == "HEAD:main" for args in git_calls)
    assert "tok-push-value" not in res.text


def test_push_falls_back_to_pr_on_rejected_push(client: TestClient, monkeypatch):
    from runtime import github

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "PushPR", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-pr-value"})

    monkeypatch.setattr(github, "default_branch", lambda url, token: "main")

    def fake_git(folder, args):
        # The direct push to the default branch is rejected; the branch push is fine.
        if args[:1] == ["push"] and args[-1] == "HEAD:main":
            return "! [rejected] main -> main (non-fast-forward)"
        return ""

    monkeypatch.setattr(github, "run_git", fake_git)
    monkeypatch.setattr(github, "open_pull_request", lambda *a, **k: "https://github.com/o/r/pull/7")

    res = client.post(f"/projects/{project['id']}/push").json()
    assert res["ok"] is True
    assert res["branch"].startswith("agent-studio/")
    assert res["prUrl"] == "https://github.com/o/r/pull/7"
