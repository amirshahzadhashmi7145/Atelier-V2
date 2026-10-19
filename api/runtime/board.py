"""Task board records: the only place agents hand work to each other."""

from __future__ import annotations

from store import db

MAX_REWORKS = 2


def write_handoff(run: dict, task: dict, summary: dict) -> dict:
    evidence = []
    for item in summary.get("criteria") or []:
        if isinstance(item, dict):
            evidence.append({"criterion": item.get("text") or "", "evidence": item.get("evidence") or ""})
        else:
            evidence.append({"criterion": str(item), "evidence": ""})
    questions = [str(item) for item in (summary.get("followUps") or []) if str(item).strip()]
    note = {
        "id": db.nid("handoff"),
        "taskId": task["id"],
        "agentId": run.get("agentId") or "",
        "summary": summary.get("description") or "",
        "filesChanged": list(summary.get("filesChanged") or []),
        "evidence": evidence,
        "openQuestions": questions,
        "createdAt": db.now(),
    }
    db.put("handoff", note["id"], note)
    return note


def write_feedback(task: dict, reviewer: dict | None, verdict: str, notes: str, items: list | None = None) -> dict:
    rows = list(items or [])
    if not rows and notes:
        rows = [{"targetKind": "criterion", "target": "", "wrong": notes, "expected": ""}]
    record = {
        "id": db.nid("revfb"),
        "taskId": task["id"],
        "reviewerAgentId": (reviewer or {}).get("id") or "",
        "verdict": verdict,
        "items": rows,
        "notes": notes,
        "createdAt": db.now(),
    }
    db.put("review-feedback", record["id"], record)
    return record


def lineage_ids(task: dict | None) -> list[str]:
    if not task:
        return []
    origin = task.get("originTaskId") or task["id"]
    ids = []
    for item in db.listing("task"):
        if item.get("id") == origin or item.get("originTaskId") == origin:
            ids.append(item["id"])
    if task["id"] not in ids:
        ids.append(task["id"])
    return ids


def last_handoff(task: dict | None) -> dict | None:
    rows = [item for item in db.listing("handoff") if item.get("taskId") in set(lineage_ids(task))]
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows[-1] if rows else None


def latest_feedback(task: dict | None) -> dict | None:
    rows = [item for item in db.listing("review-feedback") if item.get("taskId") in set(lineage_ids(task))]
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows[-1] if rows else None


def timeline(task: dict | None) -> list[dict]:
    ids = set(lineage_ids(task))
    events = []
    for item in db.listing("handoff"):
        if item.get("taskId") in ids:
            events.append({**item, "kind": "handoff"})
    for item in db.listing("review-feedback"):
        if item.get("taskId") in ids:
            events.append({**item, "kind": "feedback"})
    events.sort(key=lambda item: item.get("createdAt") or "")
    return events


def rework_packet(task: dict | None) -> str:
    if not task:
        return ""
    handoff = last_handoff(task)
    feedback = latest_feedback(task)
    if not handoff and not feedback:
        return ""
    lines = ["# Task board", f"Task: {task.get('text') or ''}"]
    criteria = task.get("acceptanceCriteria") or []
    if criteria:
        lines.append("Acceptance: " + "; ".join(str(item) for item in criteria))
    if handoff:
        lines.extend(["# Last handoff", handoff.get("summary") or "", "Files: " + ", ".join(handoff.get("filesChanged") or [])])
        for item in handoff.get("evidence") or []:
            lines.append(f"Evidence {item.get('criterion')}: {item.get('evidence')}")
        if handoff.get("openQuestions"):
            lines.append("Open questions: " + "; ".join(handoff["openQuestions"]))
    if feedback:
        lines.extend(["# Latest feedback", f"Verdict: {feedback.get('verdict')}", feedback.get("notes") or ""])
        for item in feedback.get("items") or []:
            lines.append(
                f"{item.get('targetKind') or 'criterion'} {item.get('target') or ''}: "
                f"{item.get('wrong') or ''} (expected {item.get('expected') or ''})"
            )
    return "\n".join(lines)


def detail(project_id: str, task_id: str) -> dict | None:
    task = db.get("task", task_id)
    if task is None or task.get("projectId") != project_id:
        return None
    origin = db.get("task", task.get("originTaskId") or task["id"]) or task
    return {"task": origin, "events": timeline(task)}
