"""Supervisor graph nodes. Model calls go through gateway.llm via the run loop."""

from __future__ import annotations

import time

from runtime import board, lead as leadlib, roles as rolelib
from runtime.supervisor import steps as steplib
from runtime.supervisor.state import SupervisorState
from runtime.supervisor.worker import get_runner
from store import db

# Every model call in a graph node uses the LiteLLM gateway (loop.drive / start_review).
from gateway import llm as _gateway_llm  # noqa: F401


def _layer(agent: dict | None) -> int:
    role = rolelib.of(agent)
    return int((role or {}).get("layer") or 0)


def _status_map(state: SupervisorState, task_id: str | None, step: str) -> dict[str, str]:
    current = dict(state.get("status_by_task") or {})
    if task_id:
        current[task_id] = step
    return current


def _live_children(parent_id: str) -> list[dict]:
    rows = []
    for item in leadlib.children_of(parent_id):
        if item.get("supersededBy"):
            continue
        rows.append(item)
    return rows


def _pick_worker_child(parent_id: str) -> dict | None:
    in_flight = False
    picked = None
    for child in _live_children(parent_id):
        if child.get("reviewStatus") == "approved":
            continue
        if child.get("status") in ("running", "waiting_review"):
            in_flight = True
            continue
        if child.get("status") == "failed":
            return None
        if child.get("status") == "completed" and child.get("reviewStatus") != "approved":
            in_flight = True
            continue
        if child.get("status") in ("planned", "queued", "changes_requested") and picked is None:
            picked = child
    if in_flight:
        return None
    return picked


def _all_approved(parent_id: str) -> bool:
    kids = _live_children(parent_id)
    return bool(kids) and all(item.get("reviewStatus") == "approved" for item in kids)


def plan(state: SupervisorState) -> dict:
    run = db.get("run", state["lead_run_id"])
    if run and run.get("status") not in ("completed", "failed", "cancelled"):
        from runtime.loop import drive

        drive(run["id"])
        run = db.get("run", state["lead_run_id"])
    plan_row = None
    parent = db.get("task", state["parent_task_id"])
    if parent and parent.get("planId"):
        plan_row = db.get("plan", parent["planId"])
    if plan_row is None and run:
        plan_row = leadlib.publish_plan(run)
        parent = db.get("task", state["parent_task_id"])
    kids = leadlib.children_of(state["parent_task_id"])
    task_ids = [item["id"] for item in kids]
    status = {item["id"]: "planning" for item in kids if not item.get("supersededBy")}
    if plan_row and plan_row.get("status") != "approved":
        if leadlib.settings().get("approvePlansBeforeRunning", False):
            from langgraph.types import interrupt

            updated = {
                **state,
                "plan_id": plan_row["id"],
                "task_ids": task_ids,
                "status_by_task": status,
                "waiting_plan": True,
                "phase": "dispatch",
            }
            steplib.publish(updated)
            interrupt({"planId": plan_row["id"]})
        else:
            leadlib.mark_plan_approved(state["project_id"], plan_row["id"])
            plan_row = db.get("plan", plan_row["id"])
    out = {
        "plan_id": (plan_row or {}).get("id"),
        "task_ids": task_ids,
        "status_by_task": status,
        "waiting_plan": False,
        "phase": "dispatch" if task_ids else "wrap_up",
        "current_reviewer_id": state.get("supervisor_agent_id"),
        "current_layer": _layer(db.get("agent", state["supervisor_agent_id"])),
    }
    steplib.publish({**state, **out})
    return out


def dispatch(state: SupervisorState) -> dict:
    child = _pick_worker_child(state["parent_task_id"])
    if child is None:
        phase = "wrap_up" if _all_approved(state["parent_task_id"]) or not _live_children(state["parent_task_id"]) else "wrap_up"
        out = {"current_task_id": None, "phase": phase}
        steplib.publish({**state, **out})
        return out
    worker = db.get("agent", child.get("assignedAgentId") or "")
    reviewer = db.get("agent", state.get("current_reviewer_id") or "")
    if reviewer is None:
        reviewer = rolelib.first_reviewer(db.get("project", state["project_id"]), worker) or db.get(
            "agent", state["supervisor_agent_id"]
        )
    status = _status_map(state, child["id"], "working")
    out = {
        "current_task_id": child["id"],
        "current_reviewer_id": (reviewer or {}).get("id"),
        "current_layer": _layer(reviewer),
        "status_by_task": status,
        "phase": "wait",
        "review_failed": False,
        "escalate_to_user": False,
    }
    steplib.publish({**state, **out})
    return out


def wait(state: SupervisorState) -> dict:
    task_id = state.get("current_task_id")
    if not task_id:
        out = {"phase": "wrap_up", "last_worker_status": None}
        steplib.publish({**state, **out})
        return out
    from runtime import lessons, notes

    project = db.get("project", state["project_id"]) or {}
    worker = db.get("agent", (db.get("task", task_id) or {}).get("assignedAgentId") or "") or {}
    result = get_runner().run(
        {
            "project_id": state["project_id"],
            "task_id": task_id,
            "text": "",
            "notes": notes.for_prompt(project),
            "lessons": lessons.for_prompt(worker.get("roleKey") or ""),
        }
    )
    handoff_ids = list(state.get("handoff_ids") or [])
    if result.get("handoffId") and result["handoffId"] not in handoff_ids:
        handoff_ids.append(result["handoffId"])
    worker_status = result.get("status") or "failed"
    if worker_status != "completed" or not result.get("handoffId"):
        status = _status_map(state, task_id, "escalated")
        out = {
            "handoff_ids": handoff_ids,
            "current_worker_run_id": result.get("runId"),
            "last_worker_status": worker_status,
            "status_by_task": status,
            "phase": "wrap_up",
        }
        steplib.publish({**state, **out})
        return out
    status = _status_map(state, task_id, "reviewing")
    out = {
        "handoff_ids": handoff_ids,
        "current_worker_run_id": result.get("runId"),
        "last_worker_status": worker_status,
        "status_by_task": status,
        "phase": "review",
    }
    steplib.publish({**state, **out})
    return out


def _wait_run(run_id: str | None) -> dict | None:
    from runtime import project_runs

    if not run_id:
        return None
    while True:
        run = db.get("run", run_id)
        if run is None:
            return None
        if run.get("status") not in project_runs.ACTIVE:
            return run
        time.sleep(0.05)


def review(state: SupervisorState) -> dict:
    task_id = state.get("current_task_id")
    child = db.get("task", task_id or "")
    if child is None:
        out = {"phase": "wrap_up", "review_failed": True}
        steplib.publish({**state, **out})
        return out
    reviewer_id = state.get("current_reviewer_id") or state["supervisor_agent_id"]
    reviewer = db.get("agent", reviewer_id)
    author = db.get("run", state.get("current_worker_run_id") or child.get("diffRef") or "") or {
        "id": state.get("current_worker_run_id"),
        "projectId": state["project_id"],
        "summary": child.get("summary"),
    }
    handle = leadlib.start_review(author, child, reviewer)
    run_id = (handle or {}).get("runId")
    finished = _wait_run(run_id)
    if finished is None or finished.get("status") != "completed":
        status = _status_map(state, child["id"], "escalated")
        out = {"review_failed": True, "status_by_task": status, "phase": "wrap_up"}
        steplib.publish({**state, **out})
        return out
    feedback = board.latest_feedback(db.get("task", child["id"]))
    decision_ids = list(state.get("decision_ids") or [])
    if feedback and feedback["id"] not in decision_ids:
        decision_ids.append(feedback["id"])
    out = {
        "decision_ids": decision_ids,
        "review_failed": False,
        "phase": "advance",
        "status_by_task": _status_map(state, child["id"], "reviewing"),
        "current_layer": _layer(reviewer),
    }
    steplib.publish({**state, **out})
    return out


def advance(state: SupervisorState) -> dict:
    task_id = state.get("current_task_id")
    child = db.get("task", task_id or "")
    if child is None:
        out = {"phase": "wrap_up"}
        steplib.publish({**state, **out})
        return out
    live = db.get("task", child.get("supersededBy") or child["id"]) or child
    feedback = board.latest_feedback(live) or board.latest_feedback(child)
    verdict = (feedback or {}).get("verdict") or ""
    project = db.get("project", state["project_id"])
    worker = db.get("agent", (live or child).get("assignedAgentId") or "")
    reviewer = db.get("agent", state.get("current_reviewer_id") or "")
    status = dict(state.get("status_by_task") or {})
    if verdict == "approve":
        from runtime import fit, lessons, notes

        notes.update_after_approval(project, live)
        lessons.maybe_write(live, feedback)
        fit.record_task(live)
        nxt = rolelib.next_reviewer(project, worker, reviewer)
        if nxt:
            status[live["id"]] = "reviewing"
            out = {
                "current_task_id": live["id"],
                "current_reviewer_id": nxt["id"],
                "current_layer": _layer(nxt),
                "status_by_task": status,
                "phase": "review",
            }
            steplib.publish({**state, **out})
            return out
        live["status"] = "completed"
        live["reviewStatus"] = "approved"
        if feedback:
            live["reviewNotes"] = feedback.get("notes") or ""
        db.put("task", live["id"], live)
        status[live["id"]] = "done"
        if _all_approved(state["parent_task_id"]):
            out = {"status_by_task": status, "phase": "wrap_up", "current_task_id": live["id"]}
            steplib.publish({**state, **out})
            return out
        out = {
            "status_by_task": status,
            "phase": "dispatch",
            "current_task_id": None,
            "current_reviewer_id": None,
        }
        steplib.publish({**state, **out})
        return out
    attempts = int(live.get("reviewAttempts") or live.get("reworkCount") or 0)
    if attempts <= board.MAX_REWORKS:
        retry_id = live.get("supersededBy")
        target = db.get("task", retry_id) if retry_id else live
        if target is None:
            target = live
        status[live["id"]] = "working"
        if target["id"] != live["id"]:
            status[target["id"]] = "working"
            task_ids = list(state.get("task_ids") or [])
            if target["id"] not in task_ids:
                task_ids.append(target["id"])
        else:
            task_ids = list(state.get("task_ids") or [])
        out = {
            "task_ids": task_ids,
            "current_task_id": target["id"],
            "current_reviewer_id": (reviewer or {}).get("id"),
            "current_layer": _layer(reviewer),
            "status_by_task": status,
            "phase": "dispatch",
        }
        steplib.publish({**state, **out})
        return out
    nxt = rolelib.next_reviewer(project, worker, reviewer)
    if nxt:
        live["reviewAttempts"] = 0
        live["reworkCount"] = 0
        db.put("task", live["id"], live)
        status[live["id"]] = "escalated"
        out = {
            "current_task_id": live["id"],
            "current_reviewer_id": nxt["id"],
            "current_layer": _layer(nxt),
            "status_by_task": status,
            "phase": "review",
            "escalate_to_user": False,
        }
        steplib.publish({**state, **out})
        return out
    lead = db.get("agent", state["supervisor_agent_id"]) or reviewer
    leadlib._stamp_message(
        state["project_id"],
        "A supervisor requested changes twice. Decide whether to retry or stop.",
        state["parent_task_id"],
        lead or {},
        "review",
        {"verdict": "changes_requested"},
    )
    from runtime import needs

    needs.write(
        state["project_id"],
        live["id"],
        "escalate",
        "A supervisor requested changes twice. Decide whether to retry or stop.",
        state.get("lead_run_id"),
    )
    status[live["id"]] = "escalated"
    out = {
        "status_by_task": status,
        "phase": "wrap_up",
        "escalate_to_user": True,
    }
    steplib.publish({**state, **out})
    return out


def wrap_up(state: SupervisorState) -> dict:
    parent = db.get("task", state["parent_task_id"])
    if parent:
        leadlib.finish_parent(parent)
    status = dict(state.get("status_by_task") or {})
    if _all_approved(state["parent_task_id"]):
        for task_id in state.get("task_ids") or []:
            task = db.get("task", task_id) or {}
            if not task.get("supersededBy"):
                status[task_id] = "done"
    out = {"status_by_task": status, "phase": "done", "waiting_plan": False}
    steplib.publish({**state, **out})
    return out


def after_plan(state: SupervisorState) -> str:
    return "wrap_up" if not state.get("task_ids") else "dispatch"


def after_dispatch(state: SupervisorState) -> str:
    return "wait" if state.get("current_task_id") else "wrap_up"


def after_wait(state: SupervisorState) -> str:
    return "review" if state.get("phase") == "review" else "wrap_up"


def after_review(state: SupervisorState) -> str:
    return "advance" if not state.get("review_failed") else "wrap_up"


def after_advance(state: SupervisorState) -> str:
    phase = state.get("phase") or "wrap_up"
    if phase in ("dispatch", "review", "wrap_up"):
        return phase
    return "wrap_up"
