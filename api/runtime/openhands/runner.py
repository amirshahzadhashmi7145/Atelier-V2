"""OpenHandsWorkerRunner: WorkerRunner that never changes the supervisor graph."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import quote

from gateway import keys, llm
from runtime import board, lead as leadlib, notes
from runtime.openhands import checks, packet, sandbox
from runtime.openhands.client import RunSpec, get_client
from store import db

LOG_NAME = "openhands.jsonl"
_INFLIGHT: dict[str, str] = {}
_INFLIGHT_LOCK = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_TOOL_ALIAS = {
    "terminal": "terminal",
    "cmdrun": "terminal",
    "cmdoutput": "terminal",
    "executebash": "terminal",
    "run": "terminal",
    "edit": "edit",
    "fileedit": "edit",
    "fileeditor": "edit",
    "strreplace": "edit",
    "write": "write",
    "browser": "browser",
    "browseruse": "browser",
    "tasktracker": "task_tracker",
    "task": "task_tracker",
}


def _keyed_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


class BudgetExceeded(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


def _ensure_not_cancelled(run_id: str) -> None:
    if (db.get("run", run_id) or {}).get("status") == "cancelled":
        raise RunCancelled("The run was cancelled.")


def engine_of(agent: dict | None) -> str:
    return packet.engine_value(agent)


class OpenHandsWorkerRunner:
    def run(self, task_input: dict) -> dict:
        task_id = task_input["task_id"]
        project_id = task_input["project_id"]
        with _keyed_lock(f"project:{project_id}"):
            with _keyed_lock(f"task:{task_id}"):
                task = db.get("task", task_id)
                if task is None:
                    return {"taskId": task_id, "runId": None, "handoffId": None, "status": "missing"}
                return _run_locked(task_input, task)


def _run_locked(task_input: dict, task: dict) -> dict:
    task_id = task_input["task_id"]
    project_id = task_input["project_id"]
    from runtime.supervisor.worker import _live_worker_run, _wait_run

    live = _live_worker_run(task_id)
    with _INFLIGHT_LOCK:
        owned = _INFLIGHT.get(task_id)
    if live and owned == live["id"]:
        status = _wait_run(live["id"])
        task = db.get("task", task_id) or task
        note = board.last_handoff(task)
        return {
            "taskId": task_id,
            "runId": live["id"],
            "handoffId": note["id"] if note else None,
            "status": status,
        }
    if live and owned != live["id"]:
        _fail_stale(live, "A previous worker for this task was no longer running.")
    note = board.last_handoff(task)
    if note and task.get("status") in {"completed", "approved"} and not _live_worker_run(task_id):
        return {
            "taskId": task_id,
            "runId": task.get("diffRef"),
            "handoffId": note["id"],
            "status": "completed",
        }
    project = db.get("project", project_id)
    agent = db.get("agent", task.get("assignedAgentId") or "")
    if project is None or agent is None:
        return {"taskId": task_id, "runId": None, "handoffId": None, "status": "failed"}
    last = {"taskId": task_id, "runId": None, "handoffId": None, "status": "failed"}
    for _attempt in range(board.MAX_REWORKS + 1):
        last = _one_run(project, agent, task, task_input)
        if last.get("status") == "cancelled":
            return last
        if last.get("status") == "completed" and last.get("handoffId"):
            return last
        if last.get("status") == "failed" and (db.get("run", last.get("runId") or "") or {}).get("terminalCause") == "budget":
            return last
        task = db.get("task", task_id) or task
        if int(task.get("reworkCount") or 0) > board.MAX_REWORKS:
            return last
    return last


def _fail_stale(run: dict, reason: str) -> None:
    if run.get("status") not in {"running", "queued", "waiting_client"}:
        return
    run["status"] = "failed"
    run["terminalCause"] = "error"
    run["fail"] = reason
    run["endedAt"] = db.now()
    db.put("run", run["id"], {key: value for key, value in run.items() if key != "folder"})
    db.append_event(run["id"], "RUN_FAILED", {"text": reason, "cause": "error"})


def _short_tool(item: dict) -> str:
    raw = next((str(part).strip() for part in (item.get("action"), item.get("tool_name"), item.get("name"), item.get("type")) if str(part or "").strip()), "")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw).replace("-", "_").replace(" ", "_").lower()
    for suffix in ("_action", "_observation", "_event"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.strip("_")
    return _TOOL_ALIAS.get(text.replace("_", ""), text or "tool")


def _publish_oh_event(run: dict, item: dict, n: list[int]) -> None:
    _ensure_not_cancelled(run["id"])
    blob = " ".join(str(item.get(key) or "") for key in ("type", "action", "kind")).lower()
    name = _short_tool(item)
    args = {"path": item.get("path") or "", "command": item.get("command") or ""}
    if name in set(_TOOL_ALIAS.values()):
        if any(token in blob for token in ("observation", "result", "output")):
            output = str(item.get("content") or item.get("observation") or "").strip()
            db.append_event(run["id"], "TOOL_RESULT", {"name": name, "output": output[:2000]})
        else:
            last = (db.events_for(run["id"]) or [None])[-1]
            payload = (last or {}).get("payload") or {}
            if last and last.get("type") == "TOOL_CALLED" and payload.get("name") == name and payload.get("arguments") == args:
                return
            db.append_event(run["id"], "TOOL_CALLED", {"name": name, "arguments": args})
        return
    if "observation" in blob:
        return
    raw = item.get("content")
    if isinstance(raw, list):
        text = " ".join(str(part.get("text") or "") for part in raw if isinstance(part, dict)).strip()
    else:
        text = str(raw or "").strip()
    if not text:
        return
    n[0] += 1
    call_id = f"oh_{n[0]}"
    db.append_event(run["id"], "MODEL_OUTPUT", {"modelCallId": call_id, "callId": call_id, "text": text[:6000]})


def _one_run(project: dict, agent: dict, task: dict, task_input: dict) -> dict:
    run = _open_run(project, agent, task)
    with _INFLIGHT_LOCK:
        _INFLIGHT[task["id"]] = run["id"]
    work = None
    client = None
    token = None
    try:
        from runtime.mcp import tokens

        settings = db.get("settings", "runs") or {}
        minutes = int(settings.get("maxMinutes") or 45)
        token = tokens.issue(run["id"], ttl_sec=max(60, minutes * 60))
        work = sandbox.prepare(project, task, agent)
        prompt = packet.task_packet(task, agent, project=project, notes_text=task_input.get("notes"))
        before = checks.snapshot_packages(work.folder)
        cap = leadlib.spend_cap(settings.get("maxSpendPerRunUsd"), 0)
        recorded = [0.0]
        n = [0]

        def on_cost(usd: float) -> None:
            _ensure_not_cancelled(run["id"])
            bump = float(usd or 0) - recorded[0]
            if bump > 0:
                run["costUsd"] = round(float(run.get("costUsd") or 0) + bump, 6)
                llm.record_turn_cost(run, bump)
                recorded[0] = float(usd or 0)
                # Merge into the stored doc; a blind write of the stale copy would undo a cancel/stop.
                stored = db.get("run", run["id"]) or {}
                stored["costUsd"] = run["costUsd"]
                db.put("run", run["id"], {key: value for key, value in stored.items() if key != "folder"})
            if cap is not None and run["costUsd"] > cap:
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
                on_event=lambda item: _publish_oh_event(run, item, n),
                repo_instructions=notes.read_text(project).strip(),
                backup_model=_backup_id(agent),
                backup_api_key=_backup_key(agent),
                thinking_budget=((agent.get("model") or {}).get("config") or {}).get("thinkingBudget"),
            )
        )
        sandbox.restore_host_access(work.folder)
        run["costSource"] = "openhands"
        if result.actual_model:
            run["actualModel"] = {"name": result.actual_model}
        if result.backup_used:
            run["backupUsed"] = True
            run["backupUseCount"] = int(run.get("backupUseCount") or 0) + 1
        if result.cost_usd:
            on_cost(result.cost_usd)
        elif recorded[0] == 0:
            priced = _price_events(result.events, _model_id(agent))
            if priced:
                on_cost(priced)
        _save_log(run, result.events, task)
        files = sandbox.changed_files(work.folder, project, baseline=work.baseline)
        if not files:
            files = _zone_source_files(work.folder, agent)
        run["gitDiff"] = sandbox.diff_text(work.folder, baseline=work.baseline)
        reason = checks.reject_reason(agent, run, work.folder, files, before)
        if reason:
            checks.auto_feedback(task, reason)
            _finish(run, "failed", reason, touch_task=False)
            return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
        sandbox.sync_back(work)
        sha = sandbox.commit_work(work.source, task["id"])
        _serve_preview(project, agent, run)
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
    except RunCancelled:
        _save_log(run, [{"type": "cancelled", "text": "The run was cancelled."}], task)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "cancelled"}
    except BudgetExceeded as exc:
        _save_log(run, [{"type": "budget", "text": str(exc)}], task)
        _finish(run, "failed", str(exc), cause="budget", touch_task=True)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
    except Exception as exc:
        _save_log(run, [{"type": "error", "text": keys.redact(str(exc))}], task)
        _finish(run, "failed", keys.redact(str(exc)), touch_task=True)
        return {"taskId": task["id"], "runId": run["id"], "handoffId": None, "status": "failed"}
    finally:
        with _INFLIGHT_LOCK:
            if _INFLIGHT.get(task["id"]) == run["id"]:
                _INFLIGHT.pop(task["id"], None)
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


def _serve_preview(project: dict, agent: dict, run: dict) -> None:
    """Serve the synced project folder after completion; the sandbox preview dies with the run."""
    from runtime import tools

    if os.environ.get("GATEWAY_MOCK") == "1" or not packet._needs_preview(agent):
        return
    folder = Path(project.get("folderPath") or "")
    try:
        if folder.is_dir():
            tools._preview(run, folder)
    except Exception:
        pass


def _price_events(events: list[dict], model: str) -> float:
    total = 0.0
    for item in events or []:
        usage = item.get("token_usage") or item.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        inp = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        if inp or out:
            total += llm.cost_usd(model, {"input_tokens": int(inp), "output_tokens": int(out)})
    return round(total, 6)


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
        "costSource": "openhands",
        "startedAt": db.now(),
    }
    db.put("workspace", run["id"], {"folder": project["folderPath"]})
    db.put("run", run["id"], run)
    task["status"] = "running"
    db.put("task", task["id"], task)
    db.append_event(run["id"], "RUN_STARTED", {"engine": "openhands"})
    db.append_event(run["id"], "STATE_CHANGED", {"status": "running"})
    return run


def _model_id(agent: dict) -> str:
    model = agent.get("model") or {}
    return llm.routed_model(model.get("provider"), model.get("name") or "")


def _api_key(agent: dict) -> str | None:
    model = agent.get("model") or {}
    return llm.resolve_api_key(model.get("provider"))


def _backup_id(agent: dict) -> str:
    model = agent.get("backupModel") or {}
    if not model.get("name"):
        return ""
    return llm.routed_model(model.get("provider"), model.get("name") or "")


def _backup_key(agent: dict) -> str | None:
    model = agent.get("backupModel") or {}
    if not model.get("name"):
        return None
    return llm.resolve_api_key(model.get("provider"))


def _zone_source_files(folder: Path, agent: dict) -> list[str]:
    from runtime.openhands import checks, sandbox as oh_sandbox
    from runtime.tools import _in_zones

    zones = checks.zones_of(agent)
    rows: list[str] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(folder)).replace("\\", "/")
        parts = Path(rel).parts
        if any(part in oh_sandbox.INTERNAL for part in parts):
            continue
        if Path(rel).name in oh_sandbox.LOCKFILES:
            continue
        if zones and not _in_zones(rel, zones):
            continue
        if path.suffix.lower() not in {".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".json", ".css", ".html", ".md"}:
            continue
        rows.append(rel)
    return rows


def _evidence(task: dict, files: list[str], summary: str) -> list[dict]:
    rows = []
    listed = ", ".join(files)
    for item in task.get("acceptanceCriteria") or []:
        evidence = f"Files: {listed}" if listed else str(summary or "").strip()
        if listed and summary:
            evidence = f"{summary}\nFiles: {listed}"
        rows.append({"text": str(item), "evidence": evidence})
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
    if (db.get("run", run["id"]) or {}).get("status") == "cancelled":
        run["status"] = "cancelled"
        return
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
