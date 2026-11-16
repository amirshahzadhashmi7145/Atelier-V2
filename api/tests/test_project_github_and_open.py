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


def test_push_requires_repo(client: TestClient):
    agent = _agent(client)
    project = client.post("/projects", json={"name": "NoRepo", "agentId": agent["id"]}).json()
    res = client.post(f"/projects/{project['id']}/push")
    assert res.status_code == 422
    assert "repository" in res.json()["message"].lower()


def test_push_to_default_branch(client: TestClient, monkeypatch):
    from runtime import github

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "Push", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-push-value"})

    git_calls: list[list[str]] = []

    def fake_git(folder, args):
        git_calls.append(args)
        return (0, "")

    monkeypatch.setattr(github, "default_branch", lambda url, token: "main")
    monkeypatch.setattr(github, "_git", fake_git)
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
            return (1, "! [rejected] main -> main (non-fast-forward)")
        return (0, "")

    monkeypatch.setattr(github, "_git", fake_git)
    monkeypatch.setattr(github, "open_pull_request", lambda *a, **k: "https://github.com/o/r/pull/7")

    res = client.post(f"/projects/{project['id']}/push").json()
    assert res["ok"] is True
    assert res["branch"].startswith("studio/")
    assert res["prUrl"] == "https://github.com/o/r/pull/7"


def test_push_reports_repository_not_found(client: TestClient, monkeypatch):
    from runtime import github

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "PushMissing", "agentId": agent["id"], "repoUrl": "https://github.com/o/nope"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-missing-value"})

    monkeypatch.setattr(github, "default_branch", lambda url, token: "main")
    monkeypatch.setattr(
        github,
        "_git",
        lambda folder, args: (128, "remote: Repository not found.\nfatal: repository not found")
        if args[:1] == ["push"]
        else (0, ""),
    )

    res = client.post(f"/projects/{project['id']}/push")
    assert res.status_code == 422
    assert "not found" in res.json()["message"].lower()
    # The token must never leak into the error surfaced to the client.
    assert "tok-missing-value" not in res.text


def test_publish_skips_pr_when_nothing_changed(client: TestClient, monkeypatch):
    from runtime import github, loop

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "NoChange", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-nc-value"})
    project = db.get("project", project["id"])

    prs: list[str] = []
    # `git diff --cached --quiet` returns 0 == no staged changes.
    monkeypatch.setattr(github, "_git", lambda folder, args: (0, ""))
    monkeypatch.setattr(github, "open_pull_request", lambda *a, **k: prs.append("pr") or "url")

    result = loop._publish(project, {"id": "run_nc", "projectId": project["id"], "folder": project["folderPath"], "task": "t"})
    assert result == {}
    assert prs == []  # a no-op task must not open a pull request


def test_publish_opens_pr_when_files_changed(client: TestClient, monkeypatch):
    from runtime import github, loop

    agent = _agent(client)
    project = client.post(
        "/projects", json={"name": "Changed", "agentId": agent["id"], "repoUrl": "https://github.com/o/r"}
    ).json()
    client.patch(f"/projects/{project['id']}", json={"githubToken": "tok-ch-value"})
    project = db.get("project", project["id"])

    # diff --cached --quiet returns 1 == there are staged changes; everything else ok.
    monkeypatch.setattr(
        github, "_git", lambda folder, args: (1, "") if args[:2] == ["diff", "--cached"] else (0, "")
    )
    monkeypatch.setattr(github, "open_pull_request", lambda *a, **k: "https://github.com/o/r/pull/9")

    result = loop._publish(
        project, {"id": "run_ch", "projectId": project["id"], "folder": project["folderPath"], "task": "Add dark mode"}
    )
    assert result["prUrl"] == "https://github.com/o/r/pull/9"
    # Readable branch derived from the task text + the run's short id.
    assert result["branch"] == "task/add-dark-mode-ch"


def test_start_preview_runs_server_and_returns_project(client: TestClient, monkeypatch):
    from runtime import tools

    agent = _agent(client)
    project = client.post("/projects", json={"name": "Prev", "agentId": agent["id"]}).json()

    called: list[str] = []

    def fake_preview(run, folder):
        called.append(run["projectId"])
        return {"output": "http://127.0.0.1:9191", "previewUrl": "http://127.0.0.1:9191"}

    monkeypatch.setattr(tools, "_preview", fake_preview)
    res = client.post(f"/projects/{project['id']}/preview")
    assert res.status_code == 200
    assert called == [project["id"]]


def test_start_preview_missing_project_is_404(client: TestClient):
    assert client.post("/projects/prj_missing/preview").status_code == 404


def test_create_project_imports_repo_by_cloning(client: TestClient, monkeypatch):
    from runtime import github

    calls: list[list[str]] = []

    def fake_git(folder, args):
        calls.append(args)
        if args[:1] == ["clone"]:
            (folder / args[-1]).mkdir(parents=True, exist_ok=True)  # pretend the clone created the folder
        return (0, "")

    monkeypatch.setattr(github, "_git", fake_git)
    agent = _agent(client)
    res = client.post(
        "/projects",
        json={"name": "Imported", "agentId": agent["id"], "repoUrl": "https://github.com/owner/repo", "importFromRepo": True},
    )
    assert res.status_code == 201
    assert any(a[:1] == ["clone"] for a in calls)  # it cloned instead of git init
    assert res.json()["repoUrl"] == "https://github.com/owner/repo"


def test_create_project_import_rejects_non_github_url(client: TestClient):
    agent = _agent(client)
    res = client.post(
        "/projects",
        json={"name": "Bad", "agentId": agent["id"], "repoUrl": "https://evil.example/x", "importFromRepo": True},
    )
    assert res.status_code == 422
    assert "github.com" in res.json()["message"].lower()


def test_create_project_import_reports_clone_failure_without_leaking_token(client: TestClient, monkeypatch):
    from runtime import github

    monkeypatch.setattr(
        github, "_git", lambda folder, args: (128, "remote: Repository not found.\nfatal: repository not found")
    )
    agent = _agent(client)
    res = client.post(
        "/projects",
        json={
            "name": "Missing",
            "agentId": agent["id"],
            "repoUrl": "https://github.com/owner/nope",
            "importFromRepo": True,
            "githubToken": "tok-clone-secret",
        },
    )
    assert res.status_code == 422
    assert "not found" in res.json()["message"].lower()
    assert "tok-clone-secret" not in res.text


def test_create_project_without_repo_does_not_clone(client: TestClient, monkeypatch):
    from runtime import github

    cloned: list[str] = []
    monkeypatch.setattr(github, "_git", lambda folder, args: cloned.append(args[0]) or (0, ""))
    agent = _agent(client)
    # importFromRepo set but no repoUrl -> a normal empty project, no clone.
    res = client.post("/projects", json={"name": "Empty", "agentId": agent["id"], "importFromRepo": True})
    assert res.status_code == 201
    assert "clone" not in cloned


def test_github_settings_connect_lists_login_and_disconnects(client: TestClient, monkeypatch):
    # A token is validated with GitHub (mocked) and stored; it is never returned.
    monkeypatch.setattr(routes, "_github_login", lambda token: "octocat" if token else None)

    assert client.get("/settings/github").json()["connected"] is False

    res = client.put("/settings/github", json={"token": "ghp_" + "x" * 30})
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True
    assert body["login"] == "octocat"
    assert "ghp_" not in res.text  # token never echoed

    assert client.get("/settings/github").json()["connected"] is True
    assert client.delete("/settings/github").status_code == 204
    assert client.get("/settings/github").json()["connected"] is False


def test_github_settings_rejects_invalid_token(client: TestClient, monkeypatch):
    monkeypatch.setattr(routes, "_github_login", lambda token: None)
    res = client.put("/settings/github", json={"token": "nope"})
    assert res.status_code == 422


def _agent_messages(client: TestClient, project_id: str) -> list[str]:
    rows = client.get(f"/projects/{project_id}/messages").json()
    return [m["text"] for m in rows if m["role"] == "agent"]


def test_chat_push_asks_for_repo_when_none_set(client: TestClient, monkeypatch):
    from runtime import github

    monkeypatch.setattr(github, "global_token", lambda: "ghp" + "_connected")
    agent = _agent(client)
    project = client.post("/projects", json={"name": "Pushless", "agentId": agent["id"]}).json()

    client.post(f"/projects/{project['id']}/messages", json={"text": "push this to github"})
    replies = _agent_messages(client, project["id"])
    assert any("which github repository" in r.lower() for r in replies)


def test_chat_push_with_repo_url_pushes(client: TestClient, monkeypatch):
    from runtime import github

    monkeypatch.setattr(github, "global_token", lambda: "ghp" + "_connected")
    monkeypatch.setattr(
        github,
        "push_workspace",
        lambda project, folder, message: {"ok": True, "branch": "main", "prUrl": None, "repoUrl": project["repoUrl"]},
    )
    agent = _agent(client)
    project = client.post("/projects", json={"name": "Pushy", "agentId": agent["id"]}).json()

    client.post(
        f"/projects/{project['id']}/messages",
        json={"text": "push it to https://github.com/me/app"},
    )
    replies = _agent_messages(client, project["id"])
    assert any("pushed to" in r.lower() for r in replies)
    # The repo was remembered on the project, pinned to the global token.
    saved = db.get("project", project["id"])
    assert saved["repoUrl"] == "https://github.com/me/app"
    assert saved["tokenRef"] == "global"


def test_chat_start_preview_runs_and_reports_url(client: TestClient, monkeypatch):
    from runtime import tools

    monkeypatch.setattr(tools, "_preview", lambda run, folder: {"previewUrl": "http://localhost:5190"})
    agent = _agent(client)
    project = client.post("/projects", json={"name": "Previewable", "agentId": agent["id"]}).json()

    client.post(f"/projects/{project['id']}/messages", json={"text": "run the app"})
    replies = _agent_messages(client, project["id"])
    assert any("http://localhost:5190" in r for r in replies)


def test_preview_start_detector_ignores_stop_and_plain_run():
    from runtime import classify

    assert classify.is_preview_start("start the preview") is True
    assert classify.is_preview_start("run the app") is True
    assert classify.is_preview_start("launch the site") is True
    assert classify.is_preview_start("stop the preview") is False
    assert classify.is_preview_start("complete it") is False
