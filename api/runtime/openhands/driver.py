"""Isolated OpenHands SDK process. Reads JSON on stdin; never writes the API key."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path


def _agent_context(text: str):
    try:
        from openhands.sdk import AgentContext
        from openhands.sdk.context import Skill
    except Exception:
        try:
            from openhands.sdk.context import AgentContext, Skill
        except Exception:
            return None
    try:
        return AgentContext(skills=[Skill(name="project-notes", content=text, trigger=None)])
    except Exception:
        return None


def _secret(value: str | None):
    try:
        from pydantic import SecretStr

        return SecretStr(value) if value else None
    except Exception:
        return value


def _cost(llm, conversation) -> float:
    for obj in (llm, conversation, getattr(conversation, "conversation_stats", None)):
        metrics = getattr(obj, "metrics", None)
        if metrics is None and obj is not None:
            metrics = obj
        amount = getattr(metrics, "accumulated_cost", None)
        if amount is None:
            amount = getattr(metrics, "accumulated_cost_usd", None)
        if amount is not None:
            try:
                return round(float(amount), 6)
            except (TypeError, ValueError):
                pass
    return 0.0


def _events(conversation) -> list[dict]:
    rows = []
    state = getattr(conversation, "state", None)
    raw = getattr(state, "events", None) or getattr(conversation, "events", None) or []
    for item in raw:
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump())
        elif isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"type": type(item).__name__, "text": str(item)})
    return rows


def _questions(events: list[dict], last_text: str) -> list[str]:
    found: list[str] = []
    blob = last_text.lower()
    for item in events:
        text = str(item.get("content") or item.get("text") or item.get("message") or "")
        kind = str(item.get("type") or item.get("event_type") or "").lower()
        if "question" in kind or "wait" in kind or "blocked" in kind:
            if text.strip():
                found.append(text.strip())
        low = text.lower()
        if "blocked" in low or "need a decision" in low:
            found.append(text.strip())
    if ("?" in last_text or "blocked" in blob) and last_text.strip() and last_text.strip() not in found:
        found.append(last_text.strip()[:500])
    return found[:5]


def _provider_fail(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(
        token in text
        for token in ("timeout", "rate limit", "rate_limit", "429", "503", "502", "overloaded", "connection", "unavailable")
    )


def main() -> int:
    spec = json.loads(sys.stdin.read())
    key = os.environ.get("LLM_API_KEY")
    model = spec.get("model") or os.environ.get("LLM_MODEL") or "openai/gpt-4.1-mini"
    backup_model = os.environ.get("LLM_BACKUP_MODEL") or ""
    backup_key = os.environ.get("LLM_BACKUP_API_KEY") or key
    workspace = Path(spec["workspace"])
    timeout = int(spec.get("timeout_sec") or 2700)
    image = spec.get("server_image") or os.environ.get("OPENHANDS_SERVER_IMAGE")

    from openhands.sdk import LLM, Agent, Conversation, Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool
    from openhands.workspace import DockerWorkspace

    base_url = os.environ.get("LLM_BASE_URL") or None
    llm = LLM(model=model, api_key=_secret(key), base_url=base_url)
    kwargs = {
        "llm": llm,
        "tools": [
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
        ],
        "mcp_config": spec.get("mcp") or {},
    }
    instructions = spec.get("repo_instructions") or ""
    if instructions:
        context = _agent_context(instructions)
        if context is not None:
            kwargs["agent_context"] = context
    agent = Agent(**kwargs)
    error = None
    conversation = None
    used_backup = False
    actual = model

    def _talk(agent_obj) -> object:
        conv = Conversation(agent=agent_obj, workspace=ws)
        conv.send_message(spec.get("prompt") or "")
        done = threading.Event()
        holder: list[BaseException] = []

        def _run() -> None:
            try:
                conv.run()
            except BaseException as exc:  # noqa: BLE001
                holder.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        if not done.wait(timeout):
            stop = getattr(conv, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
            raise TimeoutError("OpenHands exceeded the run time limit")
        if holder:
            raise holder[0]
        return conv

    try:
        with DockerWorkspace(server_image=image, mount_dir=str(workspace)) as ws:
            try:
                conversation = _talk(agent)
            except BaseException as exc:
                if not _provider_fail(exc):
                    raise
                try:
                    conversation = _talk(agent)
                except BaseException as exc2:
                    if backup_model and _provider_fail(exc2):
                        llm = LLM(model=backup_model, api_key=_secret(backup_key), base_url=base_url)
                        kwargs["llm"] = llm
                        agent = Agent(**kwargs)
                        used_backup = True
                        actual = backup_model
                        conversation = _talk(agent)
                    else:
                        raise
    except BaseException as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    events = _events(conversation) if conversation is not None else []
    last = ""
    if events:
        last = str(events[-1].get("content") or events[-1].get("text") or events[-1].get("message") or "")
    cost = _cost(llm, conversation) if conversation is not None else 0.0
    questions = _questions(events, last)
    for item in events:
        sys.stdout.write(json.dumps(item, default=str) + "\n")
    result = {
        "type": "result",
        "costUsd": cost,
        "summary": last or ("OpenHands failed: " + error if error else "OpenHands finished."),
        "questions": questions,
        "blocked": bool(questions) or bool(error),
        "error": error,
        "backupUsed": used_backup,
        "actualModel": actual,
        "costSource": "openhands",
    }
    sys.stdout.write(json.dumps(result, default=str) + "\n")
    sys.stdout.flush()
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
