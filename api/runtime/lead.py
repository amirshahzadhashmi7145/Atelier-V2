"""Supervisor planning, plan approval, and the review loop."""

from __future__ import annotations

from pathlib import Path

from runtime import board, contract_file, members as memberlib, roles as rolelib
from store import db


def is_lead(agent: dict | None) -> bool:
    return rolelib.is_supervisor(agent)


def lead_of(project: dict | None) -> dict | None:
    if not project:
        return None
    ranked: list[tuple[int, dict]] = []
    for agent_id in project.get("members") or []:
        agent = db.get("agent", agent_id)
        if not is_lead(agent):
            continue
        role = rolelib.of(agent)
        ranked.append((role.get("layer") if role else 0, agent))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1].get("id") or ""))
    return ranked[0][1]


def spend_cap(raw, default: float | None = 0) -> float | None:
    """Return a USD cap, or None when spend is unlimited.

    Missing values use `default`. 0 or negative means no cap.
    """
    if raw is None:
        raw = default
    if raw is None:
        return None
    value = float(raw)
    return None if value <= 0 else value


def settings() -> dict:
    current = db.get("settings", "runs") or {}
    current.setdefault("approvePlansBeforeRunning", False)
    current.setdefault("maxLessonsPerRole", 20)
    current.setdefault("maxSpendPerReviewUsd", 0)
    current.setdefault("maxSpendPerRunUsd", 0)
    current.setdefault("maxSpendPerDayUsd", 0)
    return current


def children_of(parent_id: str) -> list[dict]:
    rows = [item for item in db.listing("task") if item.get("parentTaskId") == parent_id]
    rows.sort(key=lambda item: (item.get("order") or 0, item.get("createdAt") or item.get("id") or ""))
    return rows


def _stamp_message(project_id: str, text: str, task_id: str | None, lead: dict, label: str, extra: dict | None = None) -> dict:
    message = {
        "id": db.nid("msg"),
        "projectId": project_id,
        "role": "agent",
        "text": text,
        "createdAt": db.now(),
        "label": label,
        **memberlib.stamp(lead),
    }
    if task_id:
        message["taskId"] = task_id
    if extra:
        message.update(extra)
    db.put("message", message["id"], message)
    return message


def publish_plan(run: dict) -> dict | None:
    parent = db.get("task", run.get("taskId") or "")
    if parent is None:
        return None
    items = [item for item in children_of(parent["id"]) if not rolelib.is_supervisor(db.get("agent", item.get("assignedAgentId") or ""))]
    if not items:
        parent["status"] = "completed"
        db.put("task", parent["id"], parent)
        return None
    lead = db.get("agent", run.get("agentId")) or {}
    plan_id = db.nid("plan")
    plan_items = []
    lines = []
    for index, item in enumerate(items, start=1):
        agent = db.get("agent", item.get("assignedAgentId") or "") or {}
        name = agent.get("name") or "Agent"
        criteria = item.get("acceptanceCriteria") or []
        plan_items.append(
            {
                "taskId": item["id"],
                "assignedAgentId": item.get("assignedAgentId") or "",
                "agentName": name,
                "text": item.get("text") or "",
                "acceptanceCriteria": criteria,
                "order": item.get("order") or index,
            }
        )
        lines.append(f"{index}. {name}: {(item.get('text') or '').splitlines()[0]}")
        for criterion in criteria:
            lines.append(f"   - {criterion}")
        item["status"] = "planned"
        db.put("task", item["id"], item)
    plan = {
        "id": plan_id,
        "projectId": run["projectId"],
        "parentTaskId": parent["id"],
        "leadRunId": run["id"],
        "status": "pending",
        "items": plan_items,
    }
    db.put("plan", plan_id, plan)
    parent["status"] = "waiting_plan"
    parent["planId"] = plan_id
    db.put("task", parent["id"], parent)
    _stamp_message(run["projectId"], "\n".join(lines), parent["id"], lead, "plan", {"planId": plan_id, "planItems": plan_items})
    return plan


def _apply_item_edits(plan: dict, edits: list[dict] | None) -> None:
    if not edits:
        return
    by_id = {item["taskId"]: item for item in edits if item.get("taskId")}
    updated = []
    for item in plan["items"]:
        patch = by_id.get(item["taskId"]) or {}
        if "text" in patch:
            item["text"] = patch["text"]
        if "assignedAgentId" in patch:
            item["assignedAgentId"] = patch["assignedAgentId"]
            agent = db.get("agent", item["assignedAgentId"]) or {}
            item["agentName"] = agent.get("name") or item.get("agentName")
        if "acceptanceCriteria" in patch:
            item["acceptanceCriteria"] = patch["acceptanceCriteria"]
        task = db.get("task", item["taskId"])
        if task:
            task["text"] = item["text"]
            task["assignedAgentId"] = item["assignedAgentId"]
            task["acceptanceCriteria"] = item.get("acceptanceCriteria") or []
            db.put("task", task["id"], task)
        updated.append(item)
    plan["items"] = updated


def _stamp_plan_verdict(plan_id: str) -> None:
    for item in db.listing("message"):
        if item.get("planId") == plan_id:
            item["verdict"] = "approve"
            db.put("message", item["id"], item)


def mark_plan_approved(project_id: str, plan_id: str, edits: list[dict] | None = None) -> dict:
    plan = db.get("plan", plan_id)
    if plan is None or plan.get("projectId") != project_id:
        raise KeyError("plan")
    _apply_item_edits(plan, edits)
    plan["status"] = "approved"
    db.put("plan", plan_id, plan)
    parent = db.get("task", plan["parentTaskId"])
    if parent:
        parent["status"] = "running"
        db.put("task", parent["id"], parent)
    _stamp_plan_verdict(plan_id)
    return plan


def approve_plan(project_id: str, plan_id: str, edits: list[dict] | None = None) -> dict:
    existing = db.get("plan", plan_id)
    if existing is None or existing.get("projectId") != project_id:
        raise KeyError("plan")
    already = existing.get("status") == "approved"
    plan = mark_plan_approved(project_id, plan_id, edits)
    if already:
        return plan
    from runtime.supervisor.graph import resume_supervisor

    resume_supervisor(plan["parentTaskId"], {"approved": True})
    return plan


def edit_plan(project_id: str, plan_id: str, edits: list[dict]) -> dict:
    plan = db.get("plan", plan_id)
    if plan is None or plan.get("projectId") != project_id:
        raise KeyError("plan")
    _apply_item_edits(plan, edits)
    db.put("plan", plan_id, plan)
    return plan


def start_review(author_run: dict, child: dict, reviewer: dict | None = None) -> dict | None:
    project = db.get("project", author_run.get("projectId") or "")
    worker = db.get("agent", child.get("assignedAgentId") or "") if child else None
    lead = reviewer or rolelib.first_reviewer(project, worker) or (lead_of(project) if project else None)
    if project is None or lead is None:
        return None
    child["status"] = "waiting_review"
    child["reviewerAgentId"] = lead["id"]
    db.put("task", child["id"], child)
    review_text = review_packet(child, author_run)
    from app.routes import _start_project_run

    handle = _start_project_run(project, lead, child, review_text, None, None, kind="review")
    run_id = (handle or {}).get("runId")
    if run_id:
        run = db.get("run", run_id)
        if run:
            run["kind"] = "review"
            run["reviewOfTaskId"] = child["id"]
            run["authorRunId"] = author_run["id"]
            db.put("run", run_id, run)
    return handle


def apply_review(run: dict, verdict: str, notes: str, items: list | None = None) -> dict:
    child = db.get("task", run.get("reviewOfTaskId") or run.get("taskId") or "")
    lead = db.get("agent", run.get("agentId")) or {}
    if child is None:
        return {"output": "unknown task"}
    verdict = (verdict or "").strip().lower().replace(" ", "_")
    if verdict not in ("approve", "changes_requested"):
        return {"refused": True, "reason": "verdict must be approve or changes_requested"}
    if verdict == "approve" and not board.handoff_covers_criteria(child, board.last_handoff(child)):
        return {
            "refused": True,
            "reason": "approve needs evidence on the handoff for every acceptance criterion; request changes instead",
        }
    project_id = child["projectId"]
    board.write_feedback(child, lead, verdict, notes, items)
    label = "Approved." if verdict == "approve" else "Changes requested."
    text = f"{label} {notes}".strip()
    _stamp_message(project_id, text, child["id"], lead, "review", {"verdict": verdict, "runId": run.get("id")})
    if verdict == "approve":
        child["reviewNotes"] = notes
        db.put("task", child["id"], child)
        return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
    attempts = int(child.get("reviewAttempts") or child.get("reworkCount") or 0) + 1
    child["reviewAttempts"] = attempts
    child["reworkCount"] = attempts
    child["reviewStatus"] = "changes_requested"
    child["status"] = "completed"
    parent_id = child.get("parentTaskId")
    if attempts > board.MAX_REWORKS:
        db.put("task", child["id"], child)
        return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
    origin = child.get("originTaskId") or child["id"]
    retry = {
        "id": db.nid("task"),
        "projectId": project_id,
        "parentTaskId": parent_id,
        "text": f"{child.get('text') or ''}\n\nReview notes:\n{notes}",
        "assignedAgentId": child.get("assignedAgentId") or "",
        "routedBy": "agent",
        "status": "queued",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
        "label": "task",
        "order": child.get("order") or 0,
        "acceptanceCriteria": child.get("acceptanceCriteria") or [],
        "reviewAttempts": attempts,
        "reworkCount": attempts,
        "originTaskId": origin,
        "previousTaskId": child["id"],
        "createdAt": db.now(),
    }
    child["supersededBy"] = retry["id"]
    db.put("task", child["id"], child)
    db.put("task", retry["id"], retry)
    return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}


def finish_parent(parent: dict) -> None:
    if parent.get("status") in ("completed", "failed"):
        return
    kids = children_of(parent["id"])
    open_kids = [item for item in kids if not item.get("supersededBy") and item.get("reviewStatus") != "approved"]
    if kids and open_kids:
        if all(item.get("status") == "failed" for item in open_kids):
            parent["status"] = "failed"
            parent["summary"] = "Child work failed before review."
            db.put("task", parent["id"], parent)
        return
    project = db.get("project", parent["projectId"])
    lead = lead_of(project) if project else None
    bits = []
    for item in kids:
        if item.get("reviewStatus") == "approved":
            bits.append(f"- {item.get('summary') or (item.get('text') or '').splitlines()[0]}")
    body = "What was built:\n" + ("\n".join(bits) or "- (no child tasks)")
    body += "\n\nWhat I checked: every child task was reviewed and approved.\nWhat I would do next: ship a follow-up if the user wants more."
    parent["status"] = "completed"
    parent["summary"] = body
    db.put("task", parent["id"], parent)
    if lead and project:
        _stamp_message(project["id"], body, parent["id"], lead, "task")
        folder = Path(project["folderPath"]) if project.get("folderPath") else None
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
            from runtime import tools

            preview = tools._preview({"id": parent["id"], "projectId": project["id"]}, folder)
            url = preview.get("previewUrl")
            if url:
                project["previewUrl"] = url
                db.put("project", project["id"], project)


def _author_diff(author: dict) -> str:
    if author.get("gitDiff"):
        return str(author["gitDiff"])
    diff = db.get("diff", author.get("id") or "") or {"files": []}
    lines = []
    for item in (diff.get("files") or [])[:20]:
        lines.append(f"Changed {item.get('path')}: {(item.get('after') or '')[:400]}")
    return "\n".join(lines)


def _author_build(author: dict) -> str:
    recorded = author.get("buildTest") or {}
    if recorded:
        ok = "ok" if recorded.get("ok") else "failed"
        return f"{ok}\n{(recorded.get('output') or '')[-4000:]}"
    logs = [item for item in db.listing("artifact") if item.get("runId") == author.get("id") and item.get("kind") == "log"]
    if not logs:
        return "(not run)"
    return (logs[-1].get("text") or logs[-1].get("output") or "")[-4000:] or f"{len(logs)} log artifact(s)"


def review_packet(child: dict, author_run: dict | None) -> str:
    author = author_run or {}
    criteria = child.get("acceptanceCriteria") or []
    packet = board.rework_packet(child)
    lines = [
        "# Review packet",
        f"Review this task for {child.get('assignedAgentId')}.",
        f"Task: {child.get('text') or ''}",
        f"Criteria: {'; '.join(criteria) or 'none'}",
        f"Author summary: {author.get('summary', {}).get('description') if isinstance(author.get('summary'), dict) else author.get('summary') or child.get('summary') or ''}",
        "# Git diff",
        _author_diff(author) or "(no diff)",
        "# build_test",
        _author_build(author),
    ]
    if packet:
        lines.append(packet)
    lines.append(
        "Judge only from the evidence above: the git diff and the build_test output. Do not start servers, "
        "use a browser, or raise clarifications. If evidence is insufficient, record changes_requested naming "
        "exactly what evidence is missing. Call record_review(approve or changes_requested, notes). "
        "Do not write files. Do not ask anyone to proceed."
    )
    return "\n".join(lines)


def review_system(run: dict, folder: Path | None) -> str:
    child = db.get("task", run.get("reviewOfTaskId") or run.get("taskId") or "") or {}
    author = db.get("run", run.get("authorRunId") or child.get("diffRef") or "") or {}
    project = db.get("project", run.get("projectId") or "") or {}
    members = memberlib.member_details(project) if project.get("id") else []
    lines = [review_packet(child, author), "# Members"]
    for item in members:
        lines.append(f"- {item['name']} does zones {', '.join(item.get('zones') or [])}")
    contract = contract_file.contracts_for_reader(folder, db.get("agent", run.get("agentId") or ""))
    if contract:
        lines.extend(["# API contract", contract])
    return "\n".join(lines)


def lead_system(project: dict, folder: Path | None) -> str:
    lines = ["# Project members and scope"]
    for item in memberlib.member_details(project):
        agent = db.get("agent", item["agentId"]) or {}
        scope = agent.get("scope") or {}
        role = rolelib.of(agent)
        kind = (role or {}).get("kind") or "worker"
        tags = ", ".join((role or {}).get("tags") or [])
        lines.append(
            f"- id={item['agentId']} name={item['name']} role={item.get('roleKey')} kind={kind} "
            f"tags={tags} does={', '.join(scope.get('does') or [])} never={', '.join(scope.get('neverDoes') or [])} "
            f"zones={', '.join(item.get('zones') or [])}"
        )
    if project.get("summary"):
        lines.extend(["# Project summary", project["summary"]])
    contract = contract_file.contracts_for_reader(folder, None)
    if contract:
        lines.extend(["# API contract", contract])
    lines.append(
        "Create each worker task once with create_task, then call complete. Assign only worker roles. "
        "Never assign a supervisor as a task owner. Higher-layer supervisors review through the chain. "
        "The graph runs workers after you finish; do not write chat asking anyone to proceed or execute. "
        "Do not write application files."
    )
    return "\n".join(lines)
