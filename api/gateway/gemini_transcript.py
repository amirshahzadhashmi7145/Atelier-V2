"""Serialize Gemini model turns for replay (thought_signature on function calls)."""

from __future__ import annotations

import base64
import json
from typing import Any

from gateway.tool_pairing import ToolPairingError


def dump_model_content(content: Any) -> dict:
    return content.model_dump(mode="json", exclude_none=True)


def load_model_content(data: dict) -> Any:
    from google.genai import types

    return types.Content.model_validate(data)


def merge_stream_model_content(existing: Any | None, chunk_content: Any) -> Any:
    """Prefer the latest candidate content from the stream (includes merged function calls)."""
    if chunk_content is None:
        return existing
    return chunk_content


def assert_gemini_thought_signatures(messages: list[dict]) -> None:
    """Gemini assistant turns with tool calls must replay stored model parts verbatim."""
    for message in messages:
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            continue
        stored = message.get("gemini_model_content")
        if not stored:
            raise ToolPairingError("internal: thought_signature lost")
        parts = (stored.get("parts") if isinstance(stored, dict) else None) or []
        call_parts = [part for part in parts if isinstance(part, dict) and part.get("function_call")]
        if len(call_parts) != len(tool_calls):
            raise ToolPairingError("internal: thought_signature lost")
        for part in call_parts:
            fc = part.get("function_call") or {}
            if fc and part.get("thought_signature") is None:
                # Model did not attach a signature on this part; nothing to preserve.
                continue
            if fc and not part.get("thought_signature"):
                raise ToolPairingError("internal: thought_signature lost")


def contents_include_stored_signatures(stored: dict, built_parts: list) -> bool:
    """Test helper: built parts still carry thought_signature from stored model content."""
    stored_parts = stored.get("parts") or []
    for stored_part, built_part in zip(stored_parts, built_parts, strict=False):
        if not isinstance(stored_part, dict):
            continue
        sig = stored_part.get("thought_signature")
        if sig is None:
            continue
        built_sig = getattr(built_part, "thought_signature", None)
        if built_sig is None and isinstance(built_part, dict):
            built_sig = built_part.get("thought_signature")
        if isinstance(built_sig, bytes):
            built_sig = base64.b64encode(built_sig).decode()
        if isinstance(sig, str) and isinstance(built_sig, str):
            if sig != built_sig:
                return False
        elif sig != built_sig:
            return False
    return True
