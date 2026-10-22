"""Human input only for escalation, spend caps, and unresolved questions."""

from __future__ import annotations

from store import db

KIND = "need"
KINDS = ("escalate", "budget", "question")


def write(project_id: str | None, task_id: str | None, kind: str, question: str, run_id: str | None = None) -> dict | None:
    if kind not in KINDS or not project_id or not question:
        return None
    existing = [
        item
        for item in db.listing(KIND)
        if item.get("projectId") == project_id
        and item.get("taskId") == task_id
        and item.get("kind") == kind
        and not item.get("resolvedAt")
    ]
    if existing:
        return existing[-1]
    record = {
        "id": db.nid("need"),
        "projectId": project_id,
        "taskId": task_id,
        "runId": run_id,
        "kind": kind,
        "question": question,
        "createdAt": db.now(),
        "resolvedAt": None,
    }
    db.put(KIND, record["id"], record)
    return record


def listing(project_id: str | None = None) -> list[dict]:
    rows = [item for item in db.listing(KIND) if not item.get("resolvedAt")]
    if project_id:
        rows = [item for item in rows if item.get("projectId") == project_id]
        rows = [item for item in rows if not _answered_in_chat(item)]
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows


def resolve_open(project_id: str | None, text: str, run_id: str | None = None, resume: bool = True) -> list[dict]:
    if not project_id or not str(text).strip():
        return []
    rows = [item for item in db.listing(KIND) if not item.get("resolvedAt") and item.get("projectId") == project_id]
    if run_id:
        tied = [item for item in rows if item.get("runId") == run_id]
        if tied:
            rows = tied
    resolved = []
    for item in rows:
        row = resolve(item["id"], text, resume=resume)
        if row:
            resolved.append(row)
    return resolved


def _answered_in_chat(item: dict) -> bool:
    stamp = item.get("createdAt") or ""
    project_id = item.get("projectId")
    if not project_id:
        return False
    return any(
        (row.get("role") == "user" and (row.get("createdAt") or "") > stamp)
        for row in db.listing("message")
        if row.get("projectId") == project_id
    )


def resolve(need_id: str, text: str, resume: bool = True) -> dict | None:
    row = db.get(KIND, need_id)
    if row is None or row.get("resolvedAt"):
        return None
    from runtime import board

    task = db.get("task", row.get("taskId") or "") if row.get("taskId") else None
    if task:
        board.write_user_answer(task, text)
    run_id = row.get("runId")
    run = db.get("run", run_id or "") if run_id else None
    if resume and run and run.get("status") == "waiting_user":
        db.put("answer", run["id"], {"text": text})
        run["status"] = "running"
        db.put("run", run["id"], run)
        from runtime.loop import WAITS, wake

        if WAITS.get(run["id"]) is not None:
            wake(run["id"])
        elif run.get("kind") != "lead":
            # After a restart no thread is parked on this run; relaunch it so the answer is not lost.
            from app.worker import launch

            launch(run)
    row["resolvedAt"] = db.now()
    row["answer"] = text
    db.put(KIND, row["id"], row)
    return row
