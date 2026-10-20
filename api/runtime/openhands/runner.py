"""OpenHandsWorkerRunner: WorkerRunner that never changes the supervisor graph."""

from __future__ import annotations

import json
from urllib.parse import quote

from gateway import keys, llm
from runtime import board, notes
from runtime.openhands import checks, packet, sandbox
from runtime.openhands.client import RunSpec, get_client
from store import db

LOG_NAME = "openhands.jsonl"


class BudgetExceeded(RuntimeError):
    pass


def engine_of(agent: dict | None) -> str:
    return packet.engine_value(agent)


class OpenHandsWorkerRunner:
    def run(self, task_input: dict) -> dict:
        task_id = task_input["task_id"]
        project_id = task_input["project_id"]
        task = db.get("task", task_id)
        if task is None:
            return {"taskId": task_id, "runId": None, "handoffId": None, "status": "missing"}
        project = db.get("project", project_id)
        agent = db.get("agent", task.get("assignedAgentId") or "")
        if project is None or agent is None:
            return {"taskId": task_id, "runId": None, "handoffId": None, "status": "failed"}
        last = {"taskId": task_id, "runId": None, "handoffId": None, "status": "failed"}
        for _attempt in range(board.MAX_REWORKS + 1):
            last = _one_run(project, agent, task, task_input)
            if last.get("status") == "completed" and last.get("handoffId"):
                return last
            if last.get("status") == "failed" and (db.get("run", last.get("runId") or "") or {}).get("terminalCause") == "budget":
                return last
            task = db.get("task", task_id) or task
            if int(task.get("reworkCount") or 0) > board.MAX_REWORKS:
                return last
        return last


def _one_run(project: dict, agent: dict, task: dict, task_input: dict) -> dict:
    run = _open_run(project, agent, task)
    work = None
    client = None
    token = None
    try:
        from runtime.mcp import tokens

        settings = db.get("settings", "runs") or {}
        minutes = int(settings.get("maxMinutes") or 45)
        token = tokens.issue(run["id"], ttl_sec=max(60, minutes * 60))
        prompt = packet.task_packet(task, agent, project=project, notes_text=task_input.get("notes"))
        work = sandbox.prepare(project, task)
        before = checks.snapshot_packages(work.folder)
        cap = float(5 if settings.get("maxSpendPerRunUsd") is None else settings.get("maxSpendPerRunUsd"))
        recorded = [0.0]

        def on_cost(usd: float) -> None:
            bump = float(usd or 0) - recorded[0]
            if bump > 0:
                run["costUsd"] = round(float(run.get("costUsd") or 0) + bump, 6)
                llm.record_turn_cost(run, bump)
                recorded[0] = float(usd or 0)
                db.put("run", run["id"], {key: value for key, value in run.items() if key != "folder"})
            if run["costUsd"] > cap:
                raise BudgetExceeded("The run exceeded the spend cap.")

        client = get_client()
        result = client.run(
            RunSpec(
                workspace=work.folder,
                prompt=prompt,
                model=_model_id(agent),
                api_key=_api_key(agent),
                mcp=packet.mcp_config(agent, token=token),
                timeout_sec=max(30, minutes * 60),
                on_cost=on_cost,
                repo_instructions=notes.read_text(project).strip(),
            )
        )
        if result.cost_usd and recorded[0] == 0:
            on_cost(result.cost_usd)
        _save_log(run, result.events, task)
        files = sandbox.changed_files(work.folder, project)
        reason = checks.reject_reason(agent, run, work.folder, files, before)
        if reason:
            checks.auto_feedback(task, reason)
            _finish(run, "failed", reason, touch_task=False)
            return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
        sandbox.sync_back(work)
        sha = sandbox.commit_work(work.source, task["id"])
        summary = {
            "description": result.summary or "OpenHands finished the task.",
            "filesChanged": files,
            "criteria": _evidence(task, files, result.summary),
            "followUps": list(result.questions or []),
            "commitSha": sha,
        }
        handoff = board.write_handoff(run, task, summary)
        task["status"] = "completed"
        task["summary"] = summary["description"]
        task["diffRef"] = run["id"]
        db.put("task", task["id"], task)
        run["summary"] = summary
        run["commitSha"] = sha
        _finish(run, "completed", None)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": handoff["id"], "status": "completed"}
    except BudgetExceeded as exc:
        _save_log(run, [{"type": "budget", "text": str(exc)}], task)
        _finish(run, "failed", str(exc), cause="budget", touch_task=True)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
    except Exception as exc:
        _save_log(run, [{"type": "error", "text": keys.redact(str(exc))}], task)
        _finish(run, "failed", keys.redact(str(exc)), touch_task=True)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
    finally:
        if token:
            from runtime.mcp import tokens

            tokens.revoke(run["id"])
        if client is not None:
            try:
                client.cleanup()
            except Exception:
                pass
        if work is not None:
            try:
                work.cleanup()
            except Exception:
                pass


def _open_run(project: dict, agent: dict, task: dict) -> dict:
    model = agent.get("model") or {"provider": "openai", "name": "gpt-4.1-mini", "config": {}}
    run = {
        "id": db.nid("run"),
        "agentId": agent["id"],
        "projectId": project["id"],
        "taskId": task["id"],
        "promptVersionId": agent.get("activePromptVersionId") or "",
        "model": model,
        "workspace": {"kind": "scaffold", "template": "local"},
        "task": task.get("text") or "",
        "criteria": task.get("acceptanceCriteria") or [],
        "status": "running",
        "kind": "worker",
        "engine": "openhands",
        "iterations": 0,
        "tokensIn": 0,
        "tokensOut": 0,
        "costUsd": 0,
        "startedAt": db.now(),
    }
    db.put("workspace", run["id"], {"folder": project["folderPath"]})
    db.put("run", run["id"], run)
    task["status"] = "running"
    db.put("task", task["id"], task)
    db.append_event(run["id"], "RUN_STARTED", {"engine": "openhands"})
    return run


def _model_id(agent: dict) -> str:
    model = agent.get("model") or {}
    return llm.routed_model(model.get("provider"), model.get("name") or "")


def _api_key(agent: dict) -> str | None:
    model = agent.get("model") or {}
    return llm.resolve_api_key(model.get("provider"))


def _evidence(task: dict, files: list[str], summary: str) -> list[dict]:
    rows = []
    listed = ", ".join(files) or "(no files)"
    for item in task.get("acceptanceCriteria") or []:
        rows.append({"text": str(item), "evidence": f"{summary} Files: {listed}"})
    return rows


def _save_log(run: dict, events: list[dict], task: dict) -> None:
    redacted = []
    for item in events or []:
        blob = keys.redact(json.dumps(item, default=str))
        try:
            redacted.append(json.loads(blob))
        except json.JSONDecodeError:
            redacted.append({"type": "log", "text": blob})
    text = "\n".join(json.dumps(item, default=str) for item in redacted)
    artifact_id = db.nid("art")
    db.put(
        "artifact",
        artifact_id,
        {
            "id": artifact_id,
            "runId": run["id"],
            "name": LOG_NAME,
            "kind": "log",
            "text": text,
            "ok": True,
        },
    )
    logs = list(task.get("sessionLogIds") or [])
    if artifact_id not in logs:
        logs.append(artifact_id)
        task["sessionLogIds"] = logs
        db.put("task", task["id"], task)


def _finish(run: dict, status: str, text: str | None, cause: str | None = None, touch_task: bool = False) -> None:
    run["status"] = status
    run["endedAt"] = db.now()
    if cause:
        run["terminalCause"] = cause
    if text:
        db.append_event(run["id"], "RUN_FAILED" if status == "failed" else "RUN_COMPLETED", {"text": keys.redact(text)})
    db.put("run", run["id"], {key: value for key, value in run.items() if key != "folder"})
    if touch_task and status == "failed" and run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            task["status"] = "failed"
            db.put("task", task["id"], task)


def session_logs(task: dict | None) -> list[dict]:
    if not task:
        return []
    ids = set(board.lineage_ids(task))
    rows = []
    for item in db.listing("artifact"):
        if item.get("name") != LOG_NAME:
            continue
        run = db.get("run", item.get("runId") or "")
        if not run or run.get("taskId") not in ids:
            continue
        rows.append(
            {
                "runId": run["id"],
                "artifactId": item["id"],
                "url": "data:text/plain," + quote(item.get("text") or ""),
            }
        )
    return rows
