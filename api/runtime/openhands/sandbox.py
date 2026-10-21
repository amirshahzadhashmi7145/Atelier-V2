"""Copy of the project repo for one OpenHands run, always cleaned up."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

IGNORE = shutil.ignore_patterns("node_modules", ".venv", ".artifacts", "__pycache__", ".openhands")
INTERNAL = {".git", "node_modules", ".venv", ".artifacts", "__pycache__", "conversations", ".agent_tmp", ".openhands"}
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"}


class Worktree:
    def __init__(self, folder: Path, source: Path):
        self.folder = folder
        self.source = source
        self._closed = False

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        restore_host_access(self.folder)
        shutil.rmtree(self.folder, ignore_errors=True)


def git(folder: Path, args: list[str]) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Agent Studio",
        "GIT_AUTHOR_EMAIL": "agent@localhost",
        "GIT_COMMITTER_NAME": "Agent Studio",
        "GIT_COMMITTER_EMAIL": "agent@localhost",
    }
    result = subprocess.run(
        ["git", "-c", "safe.directory=*", "-c", "user.name=Agent Studio", "-c", "user.email=agent@localhost", *args],
        cwd=folder,
        capture_output=True,
        text=True,
        env=env,
    )
    return (result.stdout or "") + (result.stderr or "")


def prepare(project: dict, task: dict) -> Worktree:
    source = Path(project["folderPath"])
    source.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="oh-"))
    folder = root / "repo"
    shutil.copytree(source, folder, ignore=IGNORE, dirs_exist_ok=True)
    if not (folder / ".git").exists():
        git(folder, ["init"])
    git(folder, ["add", "-A"])
    from runtime import notes

    git(folder, ["add", "-f", "--", notes.path_for(project)])
    git(folder, ["commit", "-m", "baseline", "--allow-empty"])
    git(folder, ["checkout", "-B", f"task/{task['id']}"])
    _writable_for_container(folder)
    return Worktree(folder, source)


def _writable_for_container(folder: Path) -> None:
    for item in [folder, *folder.rglob("*")]:
        try:
            item.chmod(0o777 if item.is_dir() else 0o666)
        except OSError:
            pass


def restore_host_access(folder: Path) -> None:
    """Files written as the container user must be readable by the host process."""
    if not folder.exists():
        return
    _writable_for_container(folder)
    if _readable(folder):
        return
    image = os.environ.get("OPENHANDS_SERVER_IMAGE") or "ghcr.io/openhands/agent-server:1.51.0-python"
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "0",
                "--entrypoint",
                "chmod",
                "-v",
                f"{folder.resolve()}:/ws",
                image,
                "-R",
                "a+rwX",
                "/ws",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    _writable_for_container(folder)


def _readable(folder: Path) -> bool:
    try:
        for item in folder.rglob("*"):
            rel = item.relative_to(folder)
            if any(part in INTERNAL for part in rel.parts):
                continue
            if item.is_file():
                with item.open("rb"):
                    pass
    except OSError:
        return False
    return True


def diff_text(folder: Path) -> str:
    body = git(folder, ["diff", "HEAD"])
    extra = git(folder, ["ls-files", "--others", "--exclude-standard"])
    blob = (body + ("\n" + extra if extra.strip() else "")).strip()
    return blob[:20000]


def changed_files(folder: Path, project: dict | None = None) -> list[str]:
    names = git(folder, ["diff", "--name-only", "HEAD"]).splitlines()
    extra = git(folder, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    seen: list[str] = []
    for name in [*names, *extra]:
        path = name.strip().replace("\\", "/")
        if not path or path in seen:
            continue
        parts = Path(path).parts
        if any(part in INTERNAL for part in parts):
            continue
        if Path(path).name in LOCKFILES:
            continue
        seen.append(path)
    if project:
        from runtime import notes

        rel = notes.path_for(project)
        if rel and rel not in seen:
            status = git(folder, ["status", "--porcelain", "--ignored", "--", rel]).strip()
            if status:
                seen.append(rel)
    return seen


def commit_work(folder: Path, task_id: str) -> str:
    git(folder, ["checkout", "-B", f"task/{task_id}"])
    git(folder, ["add", "-A"])
    git(folder, ["commit", "-m", f"task {task_id}", "--allow-empty"])
    sha = git(folder, ["rev-parse", "HEAD"]).strip().splitlines()
    return next((line.strip() for line in reversed(sha) if line.strip() and " " not in line.strip()), "")


def sync_back(work: Worktree) -> None:
    dest = work.source
    dest.mkdir(parents=True, exist_ok=True)
    for path in work.folder.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(work.folder)
        if any(part in INTERNAL for part in rel.parts):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            try:
                target.chmod(0o644)
            except OSError:
                pass
        shutil.copy2(path, target)
