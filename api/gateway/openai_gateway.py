"""Model gateway facade: pairing, capture, retries, and provider routing."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from gateway import mock_turns
from gateway.exceptions import ModelTimeout
from gateway.providers import gemini as gemini_mod
from gateway.providers import registry

SCRIPTS = mock_turns.SCRIPTS
PROMPTS = mock_turns.PROMPTS


def usd(usage: dict) -> float:
    return mock_turns.usd(usage)


def gemini_api_key() -> str:
    return gemini_mod.api_key()


def _resolve_provider(explicit: str | None) -> str:
    return registry.resolve_provider(explicit)


def default_model_spec() -> dict:
    if os.environ.get("OLLAMA_BASE_URL", "").strip():
        return {"provider": "ollama", "name": (os.environ.get("OLLAMA_MODEL") or "llama3.2:3b").strip(), "config": {}}
    if gemini_api_key() and not os.environ.get("OPENAI_API_KEY"):
        return {"provider": "gemini", "name": (os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash").strip(), "config": {}}
    return {"provider": "openai", "name": "gpt-4.1-mini", "config": {}}


def model_call_error_message(exc: Exception, provider: str | None = None) -> str | None:
    text = str(exc)
    low = text.lower()
    name = type(exc).__name__
    pid = _resolve_provider(provider)
    if "missing credentials" in low or "api_key" in low:
        if pid == "gemini":
            return "Gemini API key is not configured. Set GEMINI_API_KEY in api/.env and restart the API."
        if pid == "ollama":
            return "Ollama is not configured. Set OLLAMA_BASE_URL in api/.env."
        return "OpenAI API key is not configured on the API server. Set OPENAI_API_KEY in api/.env and restart the API."
    if "429" in text or "insufficient" in low or "quota" in low or "credits" in low:
        if pid == "ollama":
            return "The local model server rejected the request (rate limit or overload). Retry in a moment or try a smaller Ollama model."
        if pid == "gemini":
            return "Gemini rejected the request (quota or rate limit). Check Google AI billing and limits."
        return (
            "OpenAI rejected the call because this account has no API credits left. "
            "Add credits in OpenAI billing, set GEMINI_API_KEY or OLLAMA_BASE_URL in api/.env, "
            "or set GATEWAY_MOCK=1 in api/.env for offline runs."
        )
    if name == "AuthenticationError" or "invalid api key" in low:
        if pid == "gemini":
            return "Gemini rejected the API key. Check GEMINI_API_KEY in api/.env."
        if pid == "ollama":
            return "Ollama rejected the API key. Check OLLAMA_API_KEY in api/.env."
        return "OpenAI rejected the API key. Check OPENAI_API_KEY in api/.env."
    if pid == "ollama" and (name in ("APIConnectionError", "APITimeoutError") or "connection" in low):
        return "Could not reach Ollama. Run `ollama serve` and check OLLAMA_BASE_URL in api/.env."
    if pid == "gemini" and (name in ("APIConnectionError", "APITimeoutError") or "connection" in low):
        return "Could not reach Gemini. Check network access and GEMINI_API_KEY in api/.env."
    if name in ("APIConnectionError", "APITimeoutError") or "connection error" in low:
        return "Could not reach the model API. Check network access and provider keys in api/.env."
    return None


def begin() -> None:
    mock_turns._defaults = 0
    if hasattr(mock_turns, "_plans"):
        mock_turns._plans.queue = None


def _timeout_message(provider: str | None, model: str) -> str:
    return f"model call timed out ({_resolve_provider(provider)}/{model})"


def _with_retries(model: str, provider: str | None, stream_factory):
    last: Exception | None = None
    for attempt in range(3):
        try:
            yield from stream_factory()
            return
        except ModelTimeout as exc:
            last = exc
            if attempt >= 2:
                raise ModelTimeout(_timeout_message(provider, model)) from exc
            yield {"kind": "retry", "attempt": attempt + 1, "reason": str(exc)}
            time.sleep(min(8, 2**attempt))
    if last:
        raise ModelTimeout(_timeout_message(provider, model)) from last


def complete(
    model: str,
    messages: list[dict],
    tools: list[dict],
    config: dict,
    *,
    run_id: str | None = None,
    call_index: int = 0,
    provider: str | None = None,
) -> dict:
    from gateway.request_capture import record
    from gateway.tool_pairing import assert_chat_tool_pairing

    assert_chat_tool_pairing(messages)
    request_payload = {"model": model, "messages": messages, "tools": tools, "config": config, "provider": _resolve_provider(provider)}
    turn: dict | None = None
    last: Exception | None = None
    for attempt in range(3):
        try:
            impl = registry.get(provider)
            for event in impl.complete(model, messages, tools, config, stream=False, tool_choice=None):
                if event["kind"] == "done":
                    turn = {k: v for k, v in event.items() if k != "kind"}
            if turn is None:
                raise RuntimeError("provider returned no completion")
            break
        except ModelTimeout as exc:
            last = exc
            if attempt >= 2:
                raise ModelTimeout(_timeout_message(provider, model)) from exc
            time.sleep(min(8, 2**attempt))
    if turn is None:
        raise ModelTimeout(_timeout_message(provider, model)) from last
    record(run_id, call_index, {"request": request_payload, "response": turn})
    return turn


def stream_turn(
    model: str,
    messages: list[dict],
    tools: list[dict],
    config: dict,
    *,
    run_id: str | None = None,
    call_index: int = 0,
    tool_choice: str | None = None,
    provider: str | None = None,
):
    from gateway.tool_pairing import assert_chat_tool_pairing

    assert_chat_tool_pairing(messages)
    yield from _stream_turn_body(
        model,
        messages,
        tools,
        config,
        run_id=run_id,
        call_index=call_index,
        tool_choice=tool_choice,
        provider=provider,
    )


def _stream_turn_body(
    model: str,
    messages: list[dict],
    tools: list[dict],
    config: dict,
    *,
    run_id: str | None,
    call_index: int,
    tool_choice: str | None,
    provider: str | None,
):
    from gateway.request_capture import record

    request_payload = {"model": model, "messages": messages, "tools": tools, "config": config, "provider": _resolve_provider(provider)}

    def factory():
        impl = registry.get(provider)
        yield from impl.complete(model, messages, tools, config, stream=True, tool_choice=tool_choice)

    done_payload = None
    for event in _with_retries(model, provider, factory):
        if event["kind"] == "retry":
            yield event
            continue
        if event["kind"] == "delta":
            yield event
        elif event["kind"] == "tool_delta":
            yield {
                "kind": "delta",
                "text": "",
                "tool": {
                    "index": event.get("index"),
                    "id": event.get("id"),
                    "name": event.get("name"),
                    "arguments": event.get("arguments"),
                },
            }
        elif event["kind"] == "done":
            done_payload = event
            yield event
    if done_payload:
        record(
            run_id,
            call_index,
            {
                "request": request_payload,
                "response": {k: v for k, v in done_payload.items() if k != "kind"},
            },
        )


def summarize(model: str, previous: str, older: str, *, provider: str | None = None) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        line = older.strip().splitlines()[-1] if older.strip() else "nothing yet"
        return f"Earlier: {line}"[:500]
    turn = complete(
        model,
        [{"role": "user", "content": "Summarise the older conversation in one short paragraph.\n" + previous + "\n" + older}],
        [],
        {},
        provider=provider,
    )
    return turn.get("content") or previous or "Earlier conversation."


def list_model_ids(provider: str | None = None) -> list[str]:
    return registry.get(provider).list_models()


def _next_mock(messages: list[dict]) -> dict:
    return mock_turns.next_mock(messages)
