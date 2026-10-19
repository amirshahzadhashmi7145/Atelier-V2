"""Supervisor graph state: ids and status, never copies of board records."""

from __future__ import annotations

from typing import NotRequired, TypedDict

STEPS = ("planning", "working", "reviewing", "escalated", "done")


class SupervisorState(TypedDict):
    project_id: str
    parent_task_id: str
    supervisor_agent_id: str
    lead_run_id: str
    plan_id: NotRequired[str | None]
    task_ids: list[str]
    status_by_task: dict[str, str]
    decision_ids: list[str]
    handoff_ids: list[str]
    current_layer: int
    current_task_id: NotRequired[str | None]
    current_reviewer_id: NotRequired[str | None]
    current_worker_run_id: NotRequired[str | None]
    phase: NotRequired[str]
    waiting_plan: NotRequired[bool]
    escalate_to_user: NotRequired[bool]
    review_failed: NotRequired[bool]
    last_worker_status: NotRequired[str | None]


def empty_state(
    *,
    project_id: str,
    parent_task_id: str,
    supervisor_agent_id: str,
    lead_run_id: str,
    current_layer: int,
) -> SupervisorState:
    return {
        "project_id": project_id,
        "parent_task_id": parent_task_id,
        "supervisor_agent_id": supervisor_agent_id,
        "lead_run_id": lead_run_id,
        "plan_id": None,
        "task_ids": [],
        "status_by_task": {},
        "decision_ids": [],
        "handoff_ids": [],
        "current_layer": current_layer,
        "current_task_id": None,
        "current_reviewer_id": None,
        "current_worker_run_id": None,
        "phase": "plan",
        "waiting_plan": False,
        "escalate_to_user": False,
        "review_failed": False,
        "last_worker_status": None,
    }
