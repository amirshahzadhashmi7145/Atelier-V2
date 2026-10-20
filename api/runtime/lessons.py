"""Short lessons per role. No task details and no project facts."""

from __future__ import annotations

import re

from store import db

DEFAULT_CAP = 20
KIND = "lesson"
REPEAT = re.compile(
    r"\b(always|never skip|must |before complete|run tests|stay inside|do not skip)\b",
    re.I,
)
PROGRESS = re.compile(r"\b(this task|this run|files changed|heading|button|implemented)\b", re.I)


def cap() -> int:
    settings = db.get("settings", "runs") or {}
    try:
        value = int(settings.get("maxLessonsPerRole") or DEFAULT_CAP)
    except (TypeError, ValueError):
        value = DEFAULT_CAP
    return max(1, value)


def for_role(role_key: str) -> list[dict]:
    rows = [item for item in db.listing(KIND) if item.get("roleKey") == role_key]
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows


def for_prompt(role_key: str) -> str:
    rows = for_role(role_key)
    if not rows:
        return "# Role lessons\n(none yet)"
    lines = ["# Role lessons", "Apply these. Do not treat them as facts about one task."]
    for item in rows:
        lines.append(f"- {item.get('text') or ''}")
    return "\n".join(lines)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _overlap(left: str, right: str) -> bool:
    words = {item for item in re.findall(r"[a-z0-9]+", _norm(left)) if len(item) > 3}
    other = {item for item in re.findall(r"[a-z0-9]+", _norm(right)) if len(item) > 3}
    if not words or not other:
        return False
    return len(words & other) >= 3


def from_feedback(feedback: dict | None) -> str | None:
    if not feedback:
        return None
    blob = str(feedback.get("notes") or "")
    for item in feedback.get("items") or []:
        if isinstance(item, dict):
            blob += "\n" + str(item.get("wrong") or "") + "\n" + str(item.get("expected") or "")
    for raw in blob.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line or PROGRESS.search(line):
            continue
        if REPEAT.search(line):
            return line.rstrip(".")[:200]
    return None


def maybe_write(task: dict | None, feedback: dict | None) -> dict | None:
    if not task:
        return None
    reworks = int(task.get("reworkCount") or task.get("reviewAttempts") or 0)
    if reworks < 1:
        return None
    text = from_feedback(feedback)
    if not text:
        return None
    agent = db.get("agent", task.get("assignedAgentId") or "") or {}
    role_key = agent.get("roleKey") or ""
    if not role_key:
        return None
    existing = for_role(role_key)
    if any(_norm(item.get("text") or "") == _norm(text) for item in existing):
        return None
    similar = next((item for item in existing if _overlap(item.get("text") or "", text)), None)
    if similar:
        similar["text"] = text
        similar["sourceTaskId"] = task["id"]
        db.put(KIND, similar["id"], similar)
        return similar
    if len(existing) >= cap():
        oldest = existing[0]
        oldest["text"] = text
        oldest["sourceTaskId"] = task["id"]
        db.put(KIND, oldest["id"], oldest)
        return oldest
    record = {
        "id": db.nid("lesson"),
        "roleKey": role_key,
        "text": text,
        "sourceTaskId": task["id"],
        "createdAt": db.now(),
    }
    db.put(KIND, record["id"], record)
    return record


def delete(role_key: str, lesson_id: str) -> bool:
    row = db.get(KIND, lesson_id)
    if row is None or row.get("roleKey") != role_key:
        return False
    db.delete(KIND, lesson_id)
    return True
