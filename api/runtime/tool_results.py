"""Non-empty tool result text for model context."""

from __future__ import annotations

import json

READ_CAP = 20_000
LOG_TAIL = 8_000


def _tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"… truncated, showing last {limit} chars …\n{text[-limit:]}"


def format_tool_result(name: str, arguments: dict, result: dict) -> str:
    if result.get("refused"):
        return f"refused: {result.get('reason') or 'unknown reason'}"
    if result.get("clarify"):
        return f"clarification needed: {result.get('clarify')}"
    if name == "files":
        op = arguments.get("op") or "read"
        if op == "read":
            body = result.get("output") if isinstance(result.get("output"), str) else ""
            if not body.strip():
                return "(file is empty)"
            if len(body) > READ_CAP:
                return _tail(body, READ_CAP) + "\n(note: file truncated at 20 kB)"
            return body
        if op == "list":
            body = str(result.get("output") or "").strip()
            return body or "(empty directory listing)"
        action = result.get("output") or op
        changed = result.get("changed")
        return f"{action}" + ("" if changed is None else f" (changed={changed})")
    if name == "load_skill":
        if result.get("alreadyLoaded"):
            skill = result.get("skill") or arguments.get("name") or "skill"
            return f"already loaded: {skill}"
        body = (result.get("output") or "").strip()
        return body or f"loaded skill: {result.get('skill') or arguments.get('name') or 'skill'}"
    if name == "build_test":
        body = str(result.get("output") or result.get("buildLog") or "").strip()
        if not body:
            ok = result.get("buildOk")
            return f"build_test finished (ok={ok})"
        return _tail(body, LOG_TAIL)
    if name == "complete":
        return "complete acknowledged"
    output = result.get("output")
    if isinstance(output, str) and output.strip():
        return output.strip()
    if output is not None:
        text = json.dumps(output)
        if text.strip():
            return text
    return f"{name} finished"
