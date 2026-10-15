"""Build and trim model message lists with intact tool-call pairing."""

from __future__ import annotations

import json

from gateway.tool_pairing import ToolPairingError, assert_chat_tool_pairing

MAX_TRANSCRIPT_MESSAGES = 80


def assistant_message(content: str | None, tool_calls: list[dict], *, gemini_model_content: dict | None = None) -> dict:
    openai_calls = []
    for call in tool_calls:
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        openai_calls.append(
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": arguments},
            }
        )
    message: dict = {"role": "assistant", "tool_calls": openai_calls}
    if content:
        message["content"] = content
    else:
        message["content"] = None
    if gemini_model_content is not None:
        message["gemini_model_content"] = gemini_model_content
    return message


def tool_message(tool_call_id: str, content: str) -> dict:
    text = (content or "").strip() or "(empty result)"
    return {"role": "tool", "tool_call_id": tool_call_id, "content": text}


def trim_transcript(transcript: list[dict], max_messages: int = MAX_TRANSCRIPT_MESSAGES) -> list[dict]:
    """Drop oldest assistant+tool groups; never leave a tool_call without its tool results."""
    trimmed = list(transcript)
    while len(trimmed) > max_messages:
        if not trimmed:
            break
        if trimmed[0].get("role") != "assistant":
            trimmed.pop(0)
            continue
        tool_calls = trimmed[0].get("tool_calls") or []
        if not tool_calls:
            trimmed.pop(0)
            continue
        block = 1 + len(tool_calls)
        if len(trimmed) < block:
            break
        del trimmed[:block]
    return trimmed


def merge_system_and_transcript(system: str, transcript: list[dict], prefix: list[dict], suffix: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": system}, *prefix, *trim_transcript(transcript), *suffix]
    assert_chat_tool_pairing(messages)
    return messages


def pairing_error_detail(messages: list[dict]) -> str:
    try:
        assert_chat_tool_pairing(messages)
    except ToolPairingError as exc:
        return str(exc)
    return "unknown pairing error"
