"""Supervisor step records for the project chat UI."""

from __future__ import annotations

from store import db
from runtime import project_runs


def _run_for_task(task_id: str) -> dict | None:
    rows = [item for item in db.listing("run") if item.get("taskId") == task_id and item.get("kind") != "lead"]
    live = [item for item in rows if item.get("status") in project_runs.ACTIVE]
    live.sort(key=lambda item: item.get("startedAt") or "")
    if live:
        return live[-1]
    rows.sort(key=lambda item: item.get("startedAt") or "")
    return rows[-1] if rows else None


def publish(state: dict) -> None:
    parent_id = state.get("parent_task_id")
    if not parent_id:
        return
    steps = []
    for task_id in state.get("task_ids") or []:
        task = db.get("task", task_id) or {}
        if task.get("supersededBy"):
            continue
        agent = db.get("agent", task.get("assignedAgentId") or "") or {}
        live = _run_for_task(task_id)
        steps.append(
            {
                "taskId": task_id,
                "step": (state.get("status_by_task") or {}).get(task_id) or "planning",
                "label": (task.get("text") or "").splitlines()[0][:80] or None,
                "runId": (live or {}).get("id"),
                "agentName": agent.get("name"),
            }
        )
    db.put(
        "supervisor-run",
        parent_id,
        {
            "id": parent_id,
            "projectId": state.get("project_id"),
            "parentTaskId": parent_id,
            "currentLayer": state.get("current_layer"),
            "steps": steps,
        },
    )


def steps_for_project(project_id: str) -> list[dict]:
    rows = []
    for item in db.listing("supervisor-run"):
        if item.get("projectId") != project_id:
            continue
        for step in item.get("steps") or []:
            row = dict(step)
            task = db.get("task", row.get("taskId") or "") or {}
            live = _run_for_task(row.get("taskId") or "")
            if live and not row.get("runId"):
                row["runId"] = live["id"]
            if not row.get("agentName"):
                agent = db.get("agent", task.get("assignedAgentId") or "") or {}
                row["agentName"] = agent.get("name")
            current = db.get("run", row.get("runId") or "") or live
            if row.get("step") in {"working", "reviewing"} and (current or {}).get("status") not in project_runs.ACTIVE:
                if (current or {}).get("status") == "completed" or task.get("status") in {"completed", "approved"}:
                    row["step"] = "done"
                elif current or task.get("status") in {"failed", "cancelled"}:
                    row["step"] = "escalated"
            rows.append(row)
    return rows
