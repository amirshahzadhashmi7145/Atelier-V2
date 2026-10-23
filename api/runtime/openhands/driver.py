"""Isolated OpenHands SDK process. Reads JSON on stdin; never writes the API key."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path


def _mcp_servers(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("mcpServers")
    if isinstance(nested, dict):
        return nested
    return raw


def _browser_tools():
    from openhands.sdk import Tool

    for module_name, attr in (
        ("openhands.tools.browser_use", "BrowserToolSet"),
        ("openhands.tools.browser_use", "BrowserUseTool"),
        ("openhands.tools.browser", "BrowserTool"),
        ("openhands.tools.browser_tool", "BrowserTool"),
    ):
        try:
            mod = __import__(module_name, fromlist=[attr])
            cls = getattr(mod, attr)
            name = getattr(cls, "name", None)
            if name:
                return [Tool(name=name)]
        except Exception:
            continue
    return []


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


def _metrics(llm, conversation) -> list:
    rows = []
    if conversation is not None:
        for stats in (
            getattr(conversation, "conversation_stats", None),
            getattr(getattr(conversation, "state", None), "stats", None),
        ):
            getter = getattr(stats, "get_combined_metrics", None) if stats is not None else None
            if callable(getter):
                try:
                    rows.append(getter())
                except Exception:
                    pass
    for obj in (llm, conversation):
        metrics = getattr(obj, "metrics", None) if obj is not None else None
        if metrics is not None:
            rows.append(metrics)
    return rows


def _tokens(llm, conversation) -> tuple[int, int]:
    inp = out = 0
    for metrics in _metrics(llm, conversation):
        usage = getattr(metrics, "accumulated_token_usage", None)
        if usage is None and isinstance(metrics, dict):
            usage = metrics.get("accumulated_token_usage")
        if usage is None:
            continue
        try:
            prompt = int(getattr(usage, "prompt_tokens", None) or (usage.get("prompt_tokens") if isinstance(usage, dict) else 0) or 0)
            completion = int(getattr(usage, "completion_tokens", None) or (usage.get("completion_tokens") if isinstance(usage, dict) else 0) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        inp = max(inp, prompt)
        out = max(out, completion)
    return inp, out


def _cost(llm, conversation, model: str = "") -> float:
    for metrics in _metrics(llm, conversation):
        amount = getattr(metrics, "accumulated_cost", None)
        if amount is None:
            amount = getattr(metrics, "accumulated_cost_usd", None)
        if amount is None and isinstance(metrics, dict):
            amount = metrics.get("accumulated_cost")
        try:
            value = round(float(amount or 0), 6)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    inp, out = _tokens(llm, conversation)
    if (inp or out) and model:
        try:
            import litellm

            value = litellm.completion_cost(model=model, prompt_tokens=inp, completion_tokens=out)
            return round(float(value or 0), 6)
        except Exception:
            pass
    return 0.0


def _short_type(value: object) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value or "")).replace("-", "_").lower()
    for suffix in ("_action", "_observation", "_event"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text.strip("_")


def _public(item: dict) -> dict:
    nested = item.get("action") if isinstance(item.get("action"), dict) else {}
    args = item.get("args") or item.get("arguments") or nested.get("args") or nested.get("inputs") or {}
    if not isinstance(args, dict):
        args = {}
    content = str(item.get("content") or item.get("text") or item.get("message") or item.get("observation") or "")
    if len(content) > 1500:
        content = content[:1500] + "…"
    action = item.get("action") if isinstance(item.get("action"), str) else (nested.get("kind") or nested.get("action") or item.get("tool_name") or item.get("name") or "")
    if not action:
        action = _short_type(item.get("type") or item.get("event_type") or item.get("kind") or "")
    return {
        "type": str(item.get("type") or item.get("event_type") or item.get("kind") or "event"),
        "source": str(item.get("source") or ""),
        "action": str(action or ""),
        "path": str(args.get("path") or item.get("path") or nested.get("path") or ""),
        "command": str(args.get("command") or args.get("cmd") or nested.get("command") or "")[:400],
        "content": content,
    }


def _emit(item: dict) -> None:
    sys.stdout.write(json.dumps(_public(item), default=str) + "\n")
    sys.stdout.flush()


def _emit_new(conversation, seen: list[int]) -> None:
    rows = _events(conversation)
    while seen[0] < len(rows):
        _emit(rows[seen[0]])
        seen[0] += 1


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


def _thinking_kwargs(budget) -> dict:
    """Map the agent's thinking-token budget onto the SDK's reasoning knobs."""
    if budget is None:
        return {}
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        return {}
    if budget <= 4096:
        effort = "low"
    elif budget <= 16384:
        effort = "medium"
    else:
        effort = "high"
    return {"extended_thinking_budget": max(1024, budget), "reasoning_effort": effort}


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
    # One wall-clock budget for the whole task, shared across provider retries.
    deadline = time.time() + timeout
    image = spec.get("server_image") or os.environ.get("OPENHANDS_SERVER_IMAGE")

    from openhands.sdk import LLM, Agent, Conversation, Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool
    from openhands.workspace import DockerWorkspace

    base_url = os.environ.get("LLM_BASE_URL") or None
    # The SDK defaults to reasoning_effort=high with a 200k thinking budget; honor
    # the agent's configured budget instead so worker turns are not maximally slow.
    llm_extra = _thinking_kwargs(spec.get("thinking_budget"))
    llm = LLM(model=model, api_key=_secret(key), base_url=base_url, **llm_extra)
    kwargs = {
        "llm": llm,
        "tools": [
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
            *_browser_tools(),
        ],
        "mcp_config": _mcp_servers(spec.get("mcp")),
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
        halt = threading.Event()
        holder: list[BaseException] = []
        seen = [0]

        def _run() -> None:
            try:
                conv.run()
            except BaseException as exc:  # noqa: BLE001
                holder.append(exc)
            finally:
                done.set()

        billed = [0.0]
        stall_sec = float(os.environ.get("OH_STALL_SEC", "360"))
        last_activity = [time.time()]

        def _watch() -> None:
            while not halt.is_set():
                before = seen[0]
                _emit_new(conv, seen)
                if seen[0] != before:
                    last_activity[0] = time.time()
                amount = _cost(llm, conv, str(getattr(llm, "model", None) or model))
                if amount > billed[0]:
                    billed[0] = amount
                    last_activity[0] = time.time()
                    sys.stdout.write(json.dumps({"type": "cost", "costUsd": amount}) + "\n")
                    sys.stdout.flush()
                halt.wait(0.2)
            _emit_new(conv, seen)

        def _stop_conv() -> None:
            stop = getattr(conv, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass

        thread = threading.Thread(target=_run, daemon=True)
        watcher = threading.Thread(target=_watch, daemon=True)
        thread.start()
        watcher.start()
        try:
            while True:
                if done.wait(5.0):
                    break
                if time.time() >= deadline:
                    _stop_conv()
                    raise TimeoutError("OpenHands exceeded the run time limit")
                if time.time() - last_activity[0] > stall_sec:
                    # A stalled session should fail fast and retry, not burn the whole budget.
                    _stop_conv()
                    raise RuntimeError(f"OpenHands stalled: no activity for {int(stall_sec)}s (stall timeout)")
            if holder:
                raise holder[0]
            return conv
        finally:
            halt.set()
            watcher.join(timeout=2)

    npm_cache = Path.home() / ".atelier" / "npm-cache"
    try:
        npm_cache.mkdir(parents=True, exist_ok=True)
        npm_cache.chmod(0o777)
    except OSError:
        npm_cache = None
    volumes = [f"{workspace.resolve()}:/workspace"]
    if npm_cache is not None:
        # Shared package cache across runs: cold npm installs dominate worker wall-clock.
        volumes.append(f"{npm_cache}:/home/openhands/.npm")
    try:
        with DockerWorkspace(
            server_image=image,
            volumes=volumes,
            working_dir="/workspace",
        ) as ws:
            try:
                conversation = _talk(agent)
            except BaseException as exc:
                if not _provider_fail(exc):
                    raise
                try:
                    conversation = _talk(agent)
                except BaseException as exc2:
                    if backup_model and _provider_fail(exc2):
                        llm = LLM(model=backup_model, api_key=_secret(backup_key), base_url=base_url, **llm_extra)
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
    cost = _cost(llm, conversation, str(getattr(llm, "model", None) or actual)) if conversation is not None else 0.0
    questions = _questions(events, last)
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
