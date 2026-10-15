import pytest

from gateway.tool_pairing import ToolPairingError, assert_chat_tool_pairing
from runtime import messages as msglib


def test_pairing_accepts_assistant_followed_by_tool():
    transcript = [
        msglib.assistant_message("", [{"id": "c1", "name": "files", "arguments": {"op": "read", "path": "a.txt"}}]),
        msglib.tool_message("c1", "hello"),
    ]
    msglib.merge_system_and_transcript("system", transcript, [{"role": "user", "content": "task"}], [])


def test_pairing_rejects_missing_tool_result():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "files", "arguments": "{}"}}], "content": None},
    ]
    with pytest.raises(ToolPairingError):
        assert_chat_tool_pairing(messages)


def test_pairing_rejects_empty_tool_content():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "files", "arguments": "{}"}}], "content": None},
        {"role": "tool", "tool_call_id": "c1", "content": "   "},
    ]
    with pytest.raises(ToolPairingError):
        assert_chat_tool_pairing(messages)


def test_transcript_pairing_after_five_tool_steps():
    transcript: list[dict] = []
    for index in range(5):
        call_id = f"call_{index}"
        transcript.append(
            msglib.assistant_message(
                "",
                [{"id": call_id, "name": "files", "arguments": {"op": "write", "path": f"src/f{index}.tsx", "content": "x"}}],
            )
        )
        transcript.append(msglib.tool_message(call_id, f"wrote file {index}"))
    system = "compiled\n\n# Loaded skills\nnone"
    trimmed = msglib.trim_transcript(transcript, max_messages=4)
    msglib.merge_system_and_transcript(system, trimmed, [{"role": "user", "content": "build"}], [])
    assert all(trimmed[i + 1]["tool_call_id"] == trimmed[i]["tool_calls"][0]["id"] for i in range(0, len(trimmed) - 1, 2))
