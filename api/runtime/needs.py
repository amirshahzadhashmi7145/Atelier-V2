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
    rows.sort(key=lambda item: item.get("createdAt") or "")
    return rows


def resolve(need_id: str, text: str) -> dict | None:
    row = db.get(KIND, need_id)
    if row is None or row.get("resolvedAt"):
        return None
    from runtime import board

    task = db.get("task", row.get("taskId") or "") if row.get("taskId") else None
    if task:
        board.write_user_answer(task, text)
    run_id = row.get("runId")
    run = db.get("run", run_id or "") if run_id else None
    if run and run.get("status") == "waiting_user":
        db.put("answer", run["id"], {"text": text})
        run["status"] = "running"
        db.put("run", run["id"], run)
        from runtime.loop import wake

        wake(run["id"])
    row["resolvedAt"] = db.now()
    row["answer"] = text
    db.put(KIND, row["id"], row)
    return row
