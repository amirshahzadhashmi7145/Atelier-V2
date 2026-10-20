"""One generic supervisor graph. Role data changes behaviour; this code does not."""

from __future__ import annotations

import threading

from langgraph.graph import END, START, StateGraph

from runtime import roles as rolelib
from runtime.supervisor.checkpointer import get_checkpointer
from runtime.supervisor.nodes import (
    advance,
    after_advance,
    after_dispatch,
    after_plan,
    after_review,
    after_wait,
    dispatch,
    plan,
    review,
    wait,
    wrap_up,
)
from runtime.supervisor.state import SupervisorState, empty_state
from store import db

_compiled = None
_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}


def build():
    graph = StateGraph(SupervisorState)
    graph.add_node("plan", plan)
    graph.add_node("dispatch", dispatch)
    graph.add_node("wait", wait)
    graph.add_node("review", review)
    graph.add_node("advance", advance)
    graph.add_node("wrap_up", wrap_up)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", after_plan, {"dispatch": "dispatch", "wrap_up": "wrap_up"})
    graph.add_conditional_edges("dispatch", after_dispatch, {"wait": "wait", "wrap_up": "wrap_up"})
    graph.add_conditional_edges("wait", after_wait, {"review": "review", "wrap_up": "wrap_up"})
    graph.add_conditional_edges("review", after_review, {"advance": "advance", "wrap_up": "wrap_up"})
    graph.add_conditional_edges(
        "advance",
        after_advance,
        {"dispatch": "dispatch", "review": "review", "wrap_up": "wrap_up"},
    )
    graph.add_edge("wrap_up", END)
    return graph


def compiled():
    global _compiled
    with _lock:
        if _compiled is None:
            _compiled = build().compile(checkpointer=get_checkpointer())
        return _compiled


def reset_compiled() -> None:
    global _compiled
    from runtime.supervisor.checkpointer import reset as reset_cp
    from runtime.supervisor.worker import LoopWorkerRunner, set_runner

    with _lock:
        live = list(_threads.values())
        _threads.clear()
        _compiled = None
    for thread in live:
        thread.join(timeout=0.5)
    reset_cp()
    set_runner(LoopWorkerRunner())


def thread_config(parent_task_id: str) -> dict:
    return {"configurable": {"thread_id": parent_task_id}, "recursion_limit": 80}


def start_supervisor(run: dict) -> None:
    parent_id = run.get("taskId") or run.get("id")
    if not parent_id:
        return
    with _lock:
        live = _threads.get(parent_id)
        if live and live.is_alive():
            return
        thread = threading.Thread(target=_invoke_new, args=(run,), daemon=True, name=f"supervisor-{parent_id}")
        _threads[parent_id] = thread
        thread.start()


def resume_supervisor(parent_task_id: str, value=True) -> None:
    if not parent_task_id:
        return
    with _lock:
        live = _threads.get(parent_task_id)
    if live is not None and live.is_alive():
        live.join(timeout=5)
    with _lock:
        thread = threading.Thread(
            target=_invoke_resume,
            args=(parent_task_id, value),
            daemon=True,
            name=f"supervisor-resume-{parent_task_id}",
        )
        _threads[parent_task_id] = thread
        thread.start()


def _invoke_new(run: dict) -> None:
    from langgraph.errors import GraphInterrupt

    agent = db.get("agent", run.get("agentId") or "") or {}
    role = rolelib.of(agent)
    state = empty_state(
        project_id=run.get("projectId") or "",
        parent_task_id=run.get("taskId") or "",
        supervisor_agent_id=run.get("agentId") or "",
        lead_run_id=run.get("id") or "",
        current_layer=int((role or {}).get("layer") or 0),
    )
    graph = compiled()
    config = thread_config(state["parent_task_id"])
    try:
        graph.invoke(state, config)
    except GraphInterrupt:
        return
    except Exception as exc:
        _record_error(state.get("parent_task_id"), exc)
        return


def _invoke_resume(parent_task_id: str, value) -> None:
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Command

    graph = compiled()
    config = thread_config(parent_task_id)
    try:
        graph.invoke(Command(resume=value), config)
    except GraphInterrupt:
        return
    except Exception as exc:
        _record_error(parent_task_id, exc)
        return


def _record_error(parent_task_id: str | None, exc: Exception) -> None:
    if not parent_task_id:
        return
    db.put(
        "supervisor-error",
        parent_task_id,
        {"id": parent_task_id, "error": f"{type(exc).__name__}: {exc}"},
    )
