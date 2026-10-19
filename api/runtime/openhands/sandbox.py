"""Copy of the project repo for one OpenHands run, always cleaned up."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

IGNORE = shutil.ignore_patterns("node_modules", ".venv", ".artifacts", "__pycache__", ".openhands")


class Worktree:
    def __init__(self, folder: Path, source: Path):
        self.folder = folder
        self.source = source
        self._closed = False

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
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
    git(folder, ["commit", "-m", "baseline", "--allow-empty"])
    git(folder, ["checkout", "-B", f"task/{task['id']}"])
    return Worktree(folder, source)


def changed_files(folder: Path) -> list[str]:
    names = git(folder, ["diff", "--name-only", "HEAD"]).splitlines()
    extra = git(folder, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    seen: list[str] = []
    for name in [*names, *extra]:
        path = name.strip().replace("\\", "/")
        if not path or path.startswith(".git/") or path in seen:
            continue
        seen.append(path)
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
        if any(part in {".git", "node_modules", ".venv", ".artifacts", "__pycache__"} for part in rel.parts):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            try:
                target.chmod(0o644)
            except OSError:
                pass
        shutil.copy2(path, target)
