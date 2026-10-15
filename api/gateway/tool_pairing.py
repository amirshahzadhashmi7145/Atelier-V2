"""Chat Completions tool-call / tool-result pairing checks."""

from __future__ import annotations


class ToolPairingError(Exception):
    """Assistant tool_calls are not followed by matching tool messages."""


def assert_chat_tool_pairing(messages: list[dict]) -> None:
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") != "assistant":
            index += 1
            continue
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            index += 1
            continue
        for offset, call in enumerate(tool_calls):
            tool_index = index + 1 + offset
            if tool_index >= len(messages):
                raise ToolPairingError("tool result missing after assistant tool_calls")
            tool_message = messages[tool_index]
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
            if tool_message.get("role") != "tool":
                raise ToolPairingError("expected tool message after assistant tool_calls")
            if tool_message.get("tool_call_id") != call_id:
                raise ToolPairingError("tool_call_id mismatch")
            content = tool_message.get("content")
            if content is None or not str(content).strip():
                raise ToolPairingError("tool result content is empty")
        index += 1 + len(tool_calls)
