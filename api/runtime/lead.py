"""Team Lead planning, plan approval, and the review loop."""

from __future__ import annotations

from pathlib import Path

from runtime import contract_file, members as memberlib
from store import db


def is_lead(agent: dict | None) -> bool:
    if not agent:
        return False
    tags = (agent.get("capabilities") or {}).get("tags") or []
    blob = f"{agent.get('roleKey') or ''} {agent.get('name') or ''}".lower()
    return "supervisor" in tags or "team-lead" in blob or blob.strip() == "lead"


def lead_of(project: dict | None) -> dict | None:
    if not project:
        return None
    for agent_id in project.get("members") or []:
        agent = db.get("agent", agent_id)
        if is_lead(agent):
            return agent
    return None


def settings() -> dict:
    current = db.get("settings", "runs") or {}
    current.setdefault("approvePlansBeforeRunning", True)
    current.setdefault("maxSpendPerReviewUsd", 1)
    current.setdefault("maxSpendPerRunUsd", 5)
    current.setdefault("maxSpendPerDayUsd", 20)
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
    items = children_of(parent["id"])
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
    if not settings().get("approvePlansBeforeRunning", True):
        approve_plan(run["projectId"], plan_id)
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


def approve_plan(project_id: str, plan_id: str, edits: list[dict] | None = None) -> dict:
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
    start_next_child(plan["parentTaskId"])
    return plan


def edit_plan(project_id: str, plan_id: str, edits: list[dict]) -> dict:
    plan = db.get("plan", plan_id)
    if plan is None or plan.get("projectId") != project_id:
        raise KeyError("plan")
    _apply_item_edits(plan, edits)
    db.put("plan", plan_id, plan)
    return plan


def start_next_child(parent_id: str) -> dict | None:
    from runtime import classify as labeling

    parent = db.get("task", parent_id)
    if parent is None:
        return None
    project = db.get("project", parent["projectId"])
    if project is None:
        return None
    for child in children_of(parent_id):
        if child.get("supersededBy") or child.get("reviewStatus") == "approved":
            continue
        if child.get("status") in ("running", "waiting_review"):
            return None
        if child.get("status") == "failed":
            return None
        if child.get("status") == "completed" and child.get("reviewStatus") != "approved":
            return None
        if child.get("status") in ("planned", "queued", "changes_requested"):
            agent = db.get("agent", child.get("assignedAgentId") or "") or {}
            from app.routes import _start_project_run

            child["status"] = "queued"
            db.put("task", child["id"], child)
            return _start_project_run(project, agent, child, child.get("text") or "", None, labeling.prior_context(project["id"]))
    finish_parent(parent)
    return None


def start_review(author_run: dict, child: dict) -> dict | None:
    project = db.get("project", author_run.get("projectId") or "")
    lead = lead_of(project) if project else None
    if project is None or lead is None:
        return None
    child["status"] = "waiting_review"
    db.put("task", child["id"], child)
    criteria = child.get("acceptanceCriteria") or []
    review_text = (
        f"Review this task for {child.get('assignedAgentId')}.\n"
        f"Task: {child.get('text') or ''}\n"
        f"Criteria: {'; '.join(criteria) or 'none'}\n"
        f"Author summary: {author_run.get('summary', {}).get('description') if isinstance(author_run.get('summary'), dict) else author_run.get('summary') or child.get('summary') or ''}\n"
        "Call record_review(approve or changes_requested, notes). Do not write files."
    )
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


def apply_review(run: dict, verdict: str, notes: str) -> dict:
    child = db.get("task", run.get("reviewOfTaskId") or run.get("taskId") or "")
    lead = db.get("agent", run.get("agentId")) or {}
    if child is None:
        return {"output": "unknown task"}
    verdict = (verdict or "").strip().lower().replace(" ", "_")
    if verdict not in ("approve", "changes_requested"):
        return {"refused": True, "reason": "verdict must be approve or changes_requested"}
    project_id = child["projectId"]
    label = "Approved." if verdict == "approve" else "Changes requested."
    text = f"{label} {notes}".strip()
    _stamp_message(project_id, text, child["id"], lead, "review", {"verdict": verdict, "runId": run.get("id")})
    if verdict == "approve":
        child["status"] = "completed"
        child["reviewStatus"] = "approved"
        child["reviewNotes"] = notes
        db.put("task", child["id"], child)
        start_next_child(child.get("parentTaskId") or "")
        return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
    attempts = int(child.get("reviewAttempts") or 0) + 1
    child["reviewAttempts"] = attempts
    child["reviewStatus"] = "changes_requested"
    child["status"] = "completed"
    parent_id = child.get("parentTaskId")
    if attempts > 2:
        db.put("task", child["id"], child)
        _stamp_message(
            project_id,
            "The Team Lead requested changes twice. Decide whether to retry or stop.",
            parent_id,
            lead,
            "review",
            {"verdict": "changes_requested"},
        )
        return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
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
        "createdAt": db.now(),
    }
    child["supersededBy"] = retry["id"]
    db.put("task", child["id"], child)
    db.put("task", retry["id"], retry)
    start_next_child(parent_id)
    return {"done": True, "summary": {"description": text, "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}


def finish_parent(parent: dict) -> None:
    if parent.get("status") == "completed":
        return
    kids = children_of(parent["id"])
    open_kids = [item for item in kids if not item.get("supersededBy") and item.get("reviewStatus") != "approved"]
    if kids and open_kids:
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


def review_system(run: dict, folder: Path | None) -> str:
    child = db.get("task", run.get("reviewOfTaskId") or run.get("taskId") or "") or {}
    author = db.get("run", run.get("authorRunId") or child.get("diffRef") or "") or {}
    diff = db.get("diff", author.get("id") or "") or {"files": []}
    logs = [item for item in db.listing("artifact") if item.get("runId") == author.get("id") and item.get("kind") == "log"]
    shots = [item for item in db.listing("artifact") if item.get("runId") == author.get("id") and item.get("kind") == "screenshot"]
    project = db.get("project", run.get("projectId") or "") or {}
    members = memberlib.member_details(project) if project.get("id") else []
    lines = [
        "# Review packet",
        f"Task: {child.get('text') or ''}",
        f"Criteria: {'; '.join(child.get('acceptanceCriteria') or []) or 'none'}",
        f"Author summary: {(author.get('summary') or {}).get('description') if isinstance(author.get('summary'), dict) else child.get('summary') or ''}",
        f"Test logs: {len(logs)}",
        f"Screenshots: {len(shots)}",
        "# Members",
    ]
    for item in members:
        lines.append(f"- {item['name']} does zones {', '.join(item.get('zones') or [])}")
    contract = contract_file.read_contract(folder)
    if contract:
        lines.extend(["# API contract", contract])
    for item in (diff.get("files") or [])[:20]:
        lines.append(f"Changed {item.get('path')}: {(item.get('after') or '')[:400]}")
    lines.append("Call record_review. Do not write files.")
    return "\n".join(lines)


def lead_system(project: dict, folder: Path | None) -> str:
    lines = ["# Project members and scope"]
    for item in memberlib.member_details(project):
        agent = db.get("agent", item["agentId"]) or {}
        scope = agent.get("scope") or {}
        lines.append(
            f"- id={item['agentId']} name={item['name']} role={item.get('roleKey')} "
            f"does={', '.join(scope.get('does') or [])} never={', '.join(scope.get('neverDoes') or [])} "
            f"zones={', '.join(item.get('zones') or [])}"
        )
    if project.get("summary"):
        lines.extend(["# Project summary", project["summary"]])
    contract = contract_file.read_contract(folder)
    if contract:
        lines.extend(["# API contract", contract])
    lines.append("Create child tasks with create_task before any implementation. Do not write application files.")
    return "\n".join(lines)
