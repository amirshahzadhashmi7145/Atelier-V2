"""WorkerRunner: the only way the supervisor graph talks to workers."""

from __future__ import annotations

import time
from typing import Protocol

from runtime import board, project_runs, roles as rolelib
from store import db

ACTIVE = project_runs.ACTIVE


class WorkerRunner(Protocol):
    def run(self, task_input: dict) -> dict:
        """Run a worker until a handoff note is written.

        task_input must include project_id and task_id. Returns ids only:
        taskId, runId, handoffId, status.
        """


class LoopWorkerRunner:
    """Current worker loop behind WorkerRunner. Session 17 adds OpenHands here."""

    def run(self, task_input: dict) -> dict:
        task_id = task_input["task_id"]
        project_id = task_input["project_id"]
        task = db.get("task", task_id)
        if task is None:
            return {"taskId": task_id, "runId": None, "handoffId": None, "status": "missing"}
        existing = next(
            (item for item in db.listing("handoff") if item.get("taskId") == task_id),
            None,
        )
        live = _live_worker_run(task_id)
        if existing and not live:
            return {
                "taskId": task_id,
                "runId": task.get("diffRef"),
                "handoffId": existing["id"],
                "status": "completed",
            }
        run_id = (live or {}).get("id") if live else _start_worker(project_id, task)
        status = _wait_run(run_id) if run_id else "failed"
        task = db.get("task", task_id) or task
        note = board.last_handoff(task)
        return {
            "taskId": task_id,
            "runId": run_id,
            "handoffId": note["id"] if note else None,
            "status": status,
        }


def _live_worker_run(task_id: str) -> dict | None:
    rows = [
        item
        for item in db.listing("run")
        if item.get("taskId") == task_id
        and item.get("kind") not in ("lead", "review")
        and item.get("status") in ACTIVE
    ]
    rows.sort(key=lambda item: item.get("startedAt") or "")
    return rows[-1] if rows else None


def _start_worker(project_id: str, task: dict) -> str | None:
    from runtime import classify as labeling
    from runtime.route_task import route_task

    project = db.get("project", project_id)
    if project is None:
        return None
    agent = db.get("agent", task.get("assignedAgentId") or "")
    if agent is None or rolelib.is_supervisor(agent):
        route_task(project, task)
        agent = db.get("agent", task.get("assignedAgentId") or "")
    if agent is None:
        return None
    from app.routes import _start_project_run

    handle = _start_project_run(project, agent, task, task.get("text") or "", None, labeling.prior_context(project_id))
    return (handle or {}).get("runId")


def _wait_run(run_id: str | None) -> str:
    if not run_id:
        return "failed"
    while True:
        run = db.get("run", run_id)
        if run is None:
            return "failed"
        if run.get("status") not in ACTIVE:
            return run.get("status") or "failed"
        time.sleep(0.05)


_runner: WorkerRunner = LoopWorkerRunner()


def get_runner() -> WorkerRunner:
    return _runner


def set_runner(runner: WorkerRunner | None) -> None:
    global _runner
    _runner = runner or LoopWorkerRunner()
