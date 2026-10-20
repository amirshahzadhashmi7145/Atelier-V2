"""Model suggestions from real task outcomes, keyed by role id."""

from __future__ import annotations

import os

from gateway import llm
from store import db

MIN_TASKS = 5
CLOSE_RATE = 0.10


def _key(role_key: str, provider: str, name: str) -> str:
    return f"{role_key}:{provider}:{name}"


def record(role_key: str, model: dict | None, *, first_try: bool, reworks: int, cost: float, live: bool | None = None) -> dict | None:
    if not role_key or not model or not model.get("name"):
        return None
    if live is None:
        live = os.environ.get("GATEWAY_MOCK") != "1"
    if not live:
        return None
    provider = model.get("provider") or "openai"
    name = model["name"]
    row_id = _key(role_key, provider, name)
    row = db.get("model-fit", row_id) or {
        "id": row_id,
        "roleKey": role_key,
        "provider": provider,
        "name": name,
        "tasks": 0,
        "firstTry": 0,
        "reworkSum": 0,
        "costSum": 0.0,
    }
    row["tasks"] = int(row.get("tasks") or 0) + 1
    if first_try:
        row["firstTry"] = int(row.get("firstTry") or 0) + 1
    row["reworkSum"] = int(row.get("reworkSum") or 0) + int(reworks or 0)
    row["costSum"] = round(float(row.get("costSum") or 0) + float(cost or 0), 6)
    db.put("model-fit", row_id, row)
    return row


def record_task(task: dict | None, live: bool | None = None) -> dict | None:
    if not task:
        return None
    agent = db.get("agent", task.get("assignedAgentId") or "") or {}
    role_key = agent.get("roleKey") or ""
    run = db.get("run", task.get("diffRef") or "") or {}
    model = run.get("model") or agent.get("model") or {}
    reworks = int(task.get("reworkCount") or task.get("reviewAttempts") or 0)
    return record(
        role_key,
        model,
        first_try=reworks == 0,
        reworks=reworks,
        cost=float(run.get("costUsd") or 0),
        live=live,
    )


def rows_for(role_key: str) -> list[dict]:
    rows = [item for item in db.listing("model-fit") if item.get("roleKey") == role_key]
    rows.sort(key=lambda item: item.get("name") or "")
    return rows


def scored(role_key: str) -> list[dict]:
    out = []
    for row in rows_for(role_key):
        tasks = int(row.get("tasks") or 0)
        first = int(row.get("firstTry") or 0)
        rate = (first / tasks) if tasks else 0.0
        avg_cost = (float(row.get("costSum") or 0) / tasks) if tasks else 0.0
        avg_rework = (float(row.get("reworkSum") or 0) / tasks) if tasks else 0.0
        out.append(
            {
                **row,
                "firstTryRate": rate,
                "avgCostUsd": round(avg_cost, 6),
                "avgRework": round(avg_rework, 4),
                "enough": tasks >= MIN_TASKS,
                "reason": (
                    f"approved first try {first} of {tasks}, about ${avg_cost:.2f} per task"
                    if tasks >= MIN_TASKS
                    else "not enough data yet"
                ),
            }
        )
    return out


def suggestion(role_key: str) -> dict | None:
    ready = [item for item in scored(role_key) if item.get("enough")]
    if not ready:
        return None
    ready.sort(key=lambda item: (-item["firstTryRate"], item["avgCostUsd"], item.get("name") or ""))
    top = ready[0]
    close = [item for item in ready if top["firstTryRate"] - item["firstTryRate"] <= CLOSE_RATE]
    close.sort(key=lambda item: (item["avgCostUsd"], item.get("name") or ""))
    winner = close[0]
    return {
        "roleKey": role_key,
        "provider": winner["provider"],
        "name": winner["name"],
        "reason": winner["reason"],
        "firstTryRate": winner["firstTryRate"],
        "avgCostUsd": winner["avgCostUsd"],
        "tasks": winner["tasks"],
    }


def default_model(role_key: str | None) -> dict | None:
    found = suggestion(role_key or "")
    if not found:
        return None
    spec = llm.default_model_spec()
    spec["provider"] = found["provider"]
    spec["name"] = found["name"]
    return spec


def overlay(name: str, role_key: str) -> dict | None:
    row = next((item for item in scored(role_key) if item.get("name") == name), None)
    pick = suggestion(role_key)
    if not row:
        return None
    return {
        "roleKey": role_key,
        "runs": row["tasks"],
        "passed": row["firstTry"],
        "avgCostUsd": row["avgCostUsd"],
        "avgRework": row["avgRework"],
        "firstTryRate": row["firstTryRate"],
        "suggested": bool(pick and pick.get("name") == name),
        "reason": row["reason"],
    }
