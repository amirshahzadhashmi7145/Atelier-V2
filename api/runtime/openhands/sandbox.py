"""Copy of the project repo for one OpenHands run, always cleaned up."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

IGNORE = shutil.ignore_patterns("node_modules", ".venv", ".artifacts", "__pycache__", ".openhands")
INTERNAL = {".git", "node_modules", ".venv", ".artifacts", "__pycache__", "conversations", ".agent_tmp", ".openhands"}
# For the throwaway build-verification copy: also skip the OpenHands session dirs and
# .git. These are written inside the worker container under a different uid with locked
# perms, so a host-uid copytree cannot read them — and the build never needs them.
VERIFY_IGNORE = shutil.ignore_patterns(
    "node_modules", ".venv", ".artifacts", "__pycache__", ".openhands", "conversations", ".agent_tmp", ".git"
)
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"}


class Worktree:
    def __init__(self, folder: Path, source: Path, baseline: str = ""):
        self.folder = folder
        self.source = source
        self.baseline = baseline
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
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "safe.directory=*", "-c", "user.name=Agent Studio", "-c", "user.email=agent@localhost", *args],
            cwd=folder,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return f"git {args[0]} timed out"
    return (result.stdout or "") + (result.stderr or "")


def prepare(project: dict, task: dict, agent: dict | None = None) -> Worktree:
    source = Path(project["folderPath"])
    source.mkdir(parents=True, exist_ok=True)
    scaffold_source(source, agent)
    root = Path(tempfile.mkdtemp(prefix="oh-"))
    folder = root / "repo"
    shutil.copytree(source, folder, ignore=IGNORE, dirs_exist_ok=True)
    if not (folder / ".git").exists():
        git(folder, ["init"])
    git(folder, ["add", "-A"])
    from runtime import notes

    git(folder, ["add", "-f", "--", notes.path_for(project)])
    git(folder, ["commit", "-m", "baseline", "--allow-empty"])
    sha = git(folder, ["rev-parse", "HEAD"]).strip().splitlines()
    baseline = next((line.strip() for line in reversed(sha) if line.strip() and " " not in line.strip()), "")
    git(folder, ["checkout", "-B", f"task/{task['id']}"])
    _writable_for_container(folder)
    return Worktree(folder, source, baseline)


def scaffold_source(source: Path, agent: dict | None) -> str | None:
    """Write the stack starter into an empty project so the agent skips ~25 setup turns."""
    if agent is None:
        return None
    try:
        meaningful = [p for p in source.iterdir() if p.name not in {".git", ".atelier", ".artifacts"}]
    except OSError:
        return None
    if meaningful:
        return None
    from runtime.scaffold import write_express_prisma, write_vite_react_ts
    from store import db

    stacks = {item["id"]: item for item in db.listing("stack")}
    for stack_id in agent.get("stackIds") or []:
        template = (stacks.get(stack_id) or {}).get("scaffoldTemplate") or ""
        if template == "vite-react-ts":
            write_vite_react_ts(source)
            return template
        if template == "express-prisma":
            write_express_prisma(source)
            return template
    return None


def _writable_for_container(folder: Path) -> None:
    for item in [folder, *folder.rglob("*")]:
        try:
            if item.is_dir():
                item.chmod(0o777)
            else:
                mode = item.stat().st_mode
                # Keep executables executable: a flat 0o666 strips node_modules/.bin
                # and the container can no longer run tsc, vite, or any binary.
                flags = 0o666 | (0o111 if mode & 0o111 else 0)
                item.chmod(flags)
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


# Generated/compiled artifacts a reviewer should never see: a 20KB minified bundle
# would otherwise fill the diff budget and hide the actual source changes.
DIFF_EXCLUDE = [
    ":(exclude)dist/**",
    ":(exclude)build/**",
    ":(exclude).next/**",
    ":(exclude)conversations/**",
    ":(exclude).agent_tmp/**",
    ":(exclude).openhands/**",
    ":(exclude)**/*.min.js",
    ":(exclude)**/*.map",
    ":(exclude)package-lock.json",
    ":(exclude)pnpm-lock.yaml",
    ":(exclude)yarn.lock",
    ":(exclude)bun.lockb",
]


def diff_text(folder: Path, baseline: str | None = None) -> str:
    body = git(folder, ["diff", baseline or "HEAD", "--", ".", *DIFF_EXCLUDE])
    extra = git(folder, ["ls-files", "--others", "--exclude-standard", "--", ".", *DIFF_EXCLUDE])
    blob = (body + ("\n" + extra if extra.strip() else "")).strip()
    return blob[:20000]


def changed_files(folder: Path, project: dict | None = None, baseline: str | None = None) -> list[str]:
    names = git(folder, ["diff", "--name-only", baseline or "HEAD"]).splitlines()
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
