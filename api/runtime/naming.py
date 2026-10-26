"""Shared, human-friendly naming for project folders, git branches, and PR titles.

Keeps one slug convention everywhere: lowercase, words joined by single hyphens,
no leading/trailing/double hyphens, length-capped. Folders and branches read like
`connect-four` / `task/add-landing-page-1041` instead of `connect-four-prj_123` /
`task/task_1041`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


def slug(text: str, max_len: int = 50) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    if len(out) > max_len:
        out = out[:max_len].rstrip("-")
    return out or "project"


def _short_id(ident: str) -> str:
    """The distinctive tail of an id like 'task_1041' -> '1041'."""
    return (ident or "").rsplit("_", 1)[-1]


def task_branch(task_text: str, ident: str) -> str:
    """A readable branch for a task run, e.g. 'task/add-dark-mode-1041'."""
    body = slug(task_text, 40)
    tail = _short_id(ident)
    return f"task/{body}-{tail}" if tail else f"task/{body}"


def push_branch(message: str) -> str:
    """A readable branch for an on-demand push that can't fast-forward."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    body = slug(message, 30)
    return f"studio/{body}-{stamp}"


def commit_message(task_text: str) -> str:
    line = " ".join((task_text or "").split()).strip()
    if not line:
        return "Update from Agent Studio"
    line = line[0].upper() + line[1:]
    return line[:72]


def pr_title(task_text: str) -> str:
    return commit_message(task_text)
