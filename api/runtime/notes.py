"""One project notes file: stable facts for workers. Supervisors keep it current."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from store import db

DEFAULT_PATH = ".atelier/NOTES.md"
DEFAULT_MAX_BYTES = 8192
NEAR_LIMIT = 0.8
KIND = "notes"

PROGRESS = re.compile(
    r"\b("
    r"implemented|this task|this run|this pass|files changed|rework|"
    r"i added|i fixed|i changed|i updated|ready for review|completed the|"
    r"heading is visible|tests passed|build passes"
    r")\b",
    re.I,
)
STABLE = re.compile(
    r"\b("
    r"stack|framework|lives in|located in|folder layout|convention|"
    r"decision:|uses |package manager|default path|api (is|lives|endpoint)|"
    r"rest api|source of truth"
    r")\b",
    re.I,
)


def path_for(project: dict | None) -> str:
    raw = ((project or {}).get("notesPath") or DEFAULT_PATH).strip() or DEFAULT_PATH
    return raw.replace("\\", "/").lstrip("/")


def max_bytes_for(project: dict | None) -> int:
    try:
        value = int((project or {}).get("notesMaxBytes") or DEFAULT_MAX_BYTES)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_BYTES
    return max(256, value)


def defaults(project: dict | None = None) -> dict:
    row = dict(project or {})
    row["notesPath"] = path_for(row)
    row["notesMaxBytes"] = max_bytes_for(row)
    return row


def abs_path(project: dict | None) -> Path | None:
    folder = (project or {}).get("folderPath")
    if not folder:
        return None
    return Path(folder) / path_for(project)


def is_protected(rel: str, project: dict | None) -> bool:
    left = (rel or "").replace("\\", "/")
    while left.startswith("./"):
        left = left[2:]
    left = left.lstrip("/")
    right = path_for(project)
    return bool(left) and left == right


def read_text(project: dict | None) -> str:
    target = abs_path(project)
    if target is None or not target.is_file():
        return ""
    try:
        return target.read_text()
    except OSError:
        return ""


def for_prompt(project: dict | None) -> str:
    rel = path_for(project)
    body = read_text(project).strip() or "(empty)"
    return f"# Project notes ({rel})\nWorkers must not edit this file.\n{body}"


def packet_block(project: dict | None) -> str:
    return for_prompt(project)


def write_text(project: dict | None, text: str) -> Path | None:
    target = abs_path(project)
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n")
    return target


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lstrip("-").strip().lower()


def _lines(text: str) -> list[str]:
    rows = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-").strip()
        if line.lower().startswith("fact:"):
            line = line[5:].strip()
        if line:
            rows.append(line)
    return rows


def facts_from_handoff(handoff: dict | None, existing: str = "") -> list[str]:
    if not handoff:
        return []
    blob = str(handoff.get("summary") or "")
    for item in handoff.get("evidence") or []:
        if isinstance(item, dict):
            blob += "\n" + str(item.get("evidence") or "")
    known = {_norm(item) for item in _lines(existing)}
    found: list[str] = []
    for raw in blob.splitlines():
        tagged = raw.strip().lower().startswith("fact:")
        line = raw.strip().lstrip("-").strip()
        if line.lower().startswith("fact:"):
            line = line[5:].strip()
        if not line:
            continue
        if PROGRESS.search(line):
            continue
        if not tagged and not STABLE.search(line):
            continue
        key = _norm(line)
        if key in known:
            continue
        known.add(key)
        found.append(line.rstrip("."))
    return found


def compact(text: str, extra: list[str], limit: int) -> str:
    rows = _lines(text) + extra
    unique: list[str] = []
    seen: set[str] = set()
    for line in rows:
        key = _norm(line)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(line.rstrip("."))
    header = "# Project notes\n"
    budget = max(64, int(limit * 0.6) - len(header.encode()))
    kept: list[str] = []
    used = 0
    for line in unique:
        chunk = f"- {line}\n"
        size = len(chunk.encode())
        if used + size > budget:
            continue
        kept.append(chunk.rstrip("\n"))
        used += size
    return header + "\n".join(kept) + ("\n" if kept else "")


def propose_and_apply(project: dict | None, task: dict | None, handoff: dict | None) -> dict | None:
    if not project or not task:
        return None
    current = read_text(project)
    facts = facts_from_handoff(handoff, current)
    if not facts:
        return None
    limit = max_bytes_for(project)
    addition = "\n".join(f"- {item}" for item in facts) + "\n"
    body = current.rstrip() + ("\n" if current.strip() else "# Project notes\n") + addition
    rewritten = False
    if len(body.encode()) >= int(limit * NEAR_LIMIT):
        body = compact(current, facts, limit)
        rewritten = True
    write_text(project, body)
    sha = _commit(project, task["id"], rewritten)
    summary = "Rewrote project notes shorter." if rewritten else "Added project notes: " + "; ".join(facts)
    return write_event(task, summary, path_for(project), sha, rewritten)


def update_after_approval(project: dict | None, task: dict | None) -> dict | None:
    from runtime import board

    return propose_and_apply(project, task, board.last_handoff(task))


def write_event(task: dict, summary: str, path: str, sha: str | None, rewritten: bool) -> dict:
    record = {
        "id": db.nid("notes"),
        "taskId": task["id"],
        "kind": KIND,
        "summary": summary,
        "path": path,
        "commitSha": sha,
        "rewritten": rewritten,
        "createdAt": db.now(),
    }
    db.put("notes", record["id"], record)
    return record


def _commit(project: dict | None, task_id: str, rewritten: bool) -> str | None:
    folder = Path((project or {}).get("folderPath") or "")
    rel = path_for(project)
    if not folder.is_dir() or not (folder / ".git").exists():
        return None
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Agent Studio",
        "GIT_AUTHOR_EMAIL": "agent@localhost",
        "GIT_COMMITTER_NAME": "Agent Studio",
        "GIT_COMMITTER_EMAIL": "agent@localhost",
    }
    message = f"notes rewrite for task {task_id}" if rewritten else f"notes update for task {task_id}"
    subprocess.run(["git", "checkout", "-B", f"task/{task_id}"], cwd=folder, capture_output=True, env=env)
    subprocess.run(["git", "add", "--", rel], cwd=folder, capture_output=True, env=env)
    subprocess.run(
        ["git", "-c", "user.name=Agent Studio", "-c", "user.email=agent@localhost", "commit", "-m", message, "--allow-empty"],
        cwd=folder,
        capture_output=True,
        env=env,
    )
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, capture_output=True, text=True, env=env)
    return (sha.stdout or "").strip() or None
