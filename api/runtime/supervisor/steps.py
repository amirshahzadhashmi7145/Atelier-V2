"""Supervisor step records for the project chat UI."""

from __future__ import annotations

from store import db


def publish(state: dict) -> None:
    parent_id = state.get("parent_task_id")
    if not parent_id:
        return
    steps = []
    for task_id in state.get("task_ids") or []:
        task = db.get("task", task_id) or {}
        if task.get("supersededBy"):
            continue
        steps.append(
            {
                "taskId": task_id,
                "step": (state.get("status_by_task") or {}).get(task_id) or "planning",
                "label": (task.get("text") or "").splitlines()[0][:80] or None,
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
            rows.append(step)
    return rows
