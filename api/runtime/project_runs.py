"""One active run per project; the rest wait in queued status."""

from store import db

ACTIVE = {"queued", "running", "waiting_client", "waiting_user"}
ORPHAN = {"queued", "running", "waiting_client"}


def reap_orphans(reason: str | None = None) -> int:
    """Fail in-process runs left behind after the API process died."""
    text = reason or "The server restarted while this run was in progress."
    count = 0
    tasks: set[str] = set()
    for run in list(db.listing("run")):
        if run.get("status") not in ORPHAN:
            continue
        run["status"] = "failed"
        run["terminalCause"] = "error"
        run["fail"] = text
        run["endedAt"] = db.now()
        db.put("run", run["id"], run)
        db.append_event(run["id"], "RUN_FAILED", {"text": text, "cause": "error"})
        if run.get("taskId"):
            tasks.add(run["taskId"])
        count += 1
    for task_id in tasks:
        task = db.get("task", task_id)
        if task and task.get("status") in {"running", "queued", "waiting_review"}:
            task["status"] = "failed"
            db.put("task", task_id, task)
    return count


def runs(project_id: str) -> list[dict]:
    return [item for item in db.listing("run") if item.get("projectId") == project_id]


def active(project_id: str) -> dict | None:
    live = [item for item in runs(project_id) if item["status"] in ("running", "waiting_client", "waiting_user")]
    if live:
        return sorted(live, key=lambda item: item.get("startedAt") or "")[-1]
    queued = [item for item in runs(project_id) if item["status"] == "queued"]
    return sorted(queued, key=lambda item: item.get("startedAt") or "")[0] if queued else None


def working(project_id: str) -> dict | None:
    return next((item for item in runs(project_id) if item["status"] in ("running", "waiting_client", "waiting_user")), None)


def drain(project_id: str) -> None:
    if working(project_id):
        return
    waiting = sorted([item for item in runs(project_id) if item["status"] == "queued"], key=lambda item: item.get("startedAt") or "")
    if not waiting:
        return
    run = waiting[0]
    run["status"] = "running"
    db.put("run", run["id"], run)
    if run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            task["status"] = "running"
            db.put("task", task["id"], task)
    from app.worker import launch

    launch(run)


def stop_all(project_id: str) -> None:
    for run in runs(project_id):
        if run["status"] not in ACTIVE:
            continue
        db.append_event(run["id"], "STATE_CHANGED", {"status": "cancelled"})
        run["status"] = "cancelled"
        run["endedAt"] = db.now()
        db.put("run", run["id"], run)
        if run.get("taskId"):
            task = db.get("task", run["taskId"])
            if task:
                task["status"] = "cancelled"
                db.put("task", task["id"], task)
        from runtime.loop import wake
        from runtime.openhands.runner import cancel_run

        wake(run["id"])
        cancel_run(run["id"])


def spend_today(project_id: str) -> float:
    day = db.now()[:10]
    record = db.get("project-spend", project_id) or {}
    if record.get("day") != day:
        return 0.0
    return float(record.get("usd") or 0)


def add_spend(project_id: str, usd: float) -> None:
    if not project_id or usd <= 0:
        return
    day = db.now()[:10]
    record = db.get("project-spend", project_id) or {}
    if record.get("day") != day:
        record = {"day": day, "usd": 0.0}
    record["usd"] = round(float(record.get("usd") or 0) + usd, 6)
    db.put("project-spend", project_id, record)
