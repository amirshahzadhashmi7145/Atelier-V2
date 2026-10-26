"""Shared GitHub push/PR helpers.

Used both by the automatic per-task publish at the end of a run (runtime.loop)
and by the on-demand "Push to GitHub" project action (app.routes). The access
token is read from the project's secret reference and is always scrubbed out of
any text returned to callers or stored in events.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from store import db


def token_for(project: dict) -> str | None:
    """Resolve the project's GitHub token from its stored reference. Never logged."""
    ref = project.get("tokenRef") or ""
    if ref == "env:GITHUB_TOKEN":
        return os.environ.get("GITHUB_TOKEN")
    if ref.startswith("file:"):
        path = db.projects_dir() / ".secrets" / ref.removeprefix("file:")
        return path.read_text().strip() if path.exists() else None
    return None


def authed_remote(url: str, token: str) -> str:
    if url.startswith("https://github.com/"):
        return "https://x-access-token:" + token + "@" + url.removeprefix("https://")
    return url


def scrub(text: str, token: str | None) -> str:
    return text.replace(token, "***") if token else text


def run_git(folder: Path, args: list[str]) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Agent Studio",
        "GIT_AUTHOR_EMAIL": "agent@localhost",
        "GIT_COMMITTER_NAME": "Agent Studio",
        "GIT_COMMITTER_EMAIL": "agent@localhost",
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "safe.directory=*", *args], cwd=folder, capture_output=True, text=True, env=env, timeout=120
        )
    except subprocess.TimeoutExpired:
        return f"git {args[0]} timed out"
    return result.stdout + result.stderr


def default_branch(url: str, token: str) -> str:
    slug = url.removeprefix("https://github.com/").removesuffix(".git")
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        repo = httpx.get(f"https://api.github.com/repos/{slug}", headers=headers, timeout=20)
    except httpx.HTTPError:
        return "main"
    return (repo.json().get("default_branch") if repo.status_code < 300 else None) or "main"


def open_pull_request(url: str, token: str, branch: str, title: str, base: str | None = None) -> str | None:
    slug = url.removeprefix("https://github.com/").removesuffix(".git")
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    base = base or default_branch(url, token)
    if branch == base:
        return None
    try:
        response = httpx.post(
            f"https://api.github.com/repos/{slug}/pulls",
            headers=headers,
            json={"title": title[:80], "head": branch, "base": base},
            timeout=20,
        )
    except httpx.HTTPError:
        return None
    if response.status_code >= 300:
        return None
    return response.json().get("html_url")


def _rejected(output: str) -> bool:
    lowered = output.lower()
    return "rejected" in lowered or "non-fast-forward" in lowered or "failed to push" in lowered


def push_workspace(project: dict, folder: Path, message: str) -> dict:
    """Commit everything in `folder` and push it to the project's repo.

    Tries the repo's default branch first (the common case for an empty or
    fast-forwardable repo). If the remote rejects that push because it has
    diverging history, falls back to a fresh branch and opens a pull request.
    Returns a result dict with the token already scrubbed from any output.
    """
    token = token_for(project)
    repo_url = project.get("repoUrl")
    if not repo_url or not token:
        return {"ok": False, "reason": "Set a GitHub repo URL and access token in project settings first."}

    remote = authed_remote(repo_url, token)
    base = default_branch(repo_url, token)
    run_git(folder, ["checkout", "-B", base])
    run_git(folder, ["add", "-A"])
    run_git(folder, ["commit", "-m", message, "--allow-empty"])

    pushed = run_git(folder, ["push", remote, f"HEAD:{base}"])
    if not _rejected(pushed):
        return {"ok": True, "branch": base, "prUrl": None, "repoUrl": repo_url, "output": scrub(pushed, token)}

    # Remote has history we can't fast-forward: open a PR from a side branch.
    branch = f"agent-studio/{db.now().replace(':', '').replace('.', '')}"
    run_git(folder, ["checkout", "-B", branch])
    branch_push = run_git(folder, ["push", remote, f"HEAD:{branch}"])
    pr = open_pull_request(repo_url, token, branch, message, base)
    return {"ok": True, "branch": branch, "prUrl": pr, "repoUrl": repo_url, "output": scrub(branch_push, token)}
