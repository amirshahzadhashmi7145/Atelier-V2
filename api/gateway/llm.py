"""Single model gateway. Live calls go through LiteLLM. Roles are not known here."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from gateway import keys, mock_turns
from gateway.exceptions import ModelTimeout, ProviderError
from gateway.providers import gemini as gemini_mod
from gateway.providers import registry

SCRIPTS = mock_turns.SCRIPTS
PROMPTS = mock_turns.PROMPTS
DEFAULT_OPENAI = "gpt-4.1-mini"
DEFAULT_GEMINI = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def usd(usage: dict) -> float:
    return mock_turns.usd(usage)


def begin() -> None:
    mock_turns._defaults = 0
    if hasattr(mock_turns, "_plans"):
        mock_turns._plans.queue = None


def _mocked() -> bool:
    return os.environ.get("GATEWAY_MOCK") == "1"


def _provider_row(provider_id: str | None) -> dict:
    if not provider_id:
        return {}
    try:
        from store import db

        return db.get("provider", provider_id) or {}
    except Exception:
        return {}


def litellm_prefix(provider: str | None) -> str:
    row = _provider_row(provider)
    return (row.get("litellmPrefix") or provider or "openai").strip()


def env_var_for(provider: str | None) -> str:
    row = _provider_row(provider)
    if row.get("envVar"):
        return row["envVar"]
    return {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": "OLLAMA_API_KEY"}.get(
        provider or "", "OPENAI_API_KEY"
    )


def resolve_api_key(provider: str | None) -> str | None:
    pid = registry.resolve_provider(provider)
    stored = keys.load(pid)
    if stored:
        return stored
    env_name = env_var_for(pid)
    value = keys.env_fallback(env_name)
    if value:
        return value
    if pid == "gemini":
        return keys.env_fallback("GOOGLE_API_KEY") or None
    return None


def has_api_key(provider: str | None = None) -> bool:
    return bool(resolve_api_key(provider) or _mocked())


def openai_api_key() -> str | None:
    return resolve_api_key("openai")


def gemini_api_key() -> str:
    return resolve_api_key("gemini") or gemini_mod.api_key() or ""


def routed_model(provider: str | None, name: str) -> str:
    """LiteLLM model id. Gateway does not know roles."""
    pid = registry.resolve_provider(provider)
    if not name:
        return litellm_prefix(pid)
    if "/" in name:
        return name
    return f"{litellm_prefix(pid)}/{name}"


def default_model_spec() -> dict:
    if os.environ.get("OLLAMA_BASE_URL", "").strip():
        return {"provider": "ollama", "name": (os.environ.get("OLLAMA_MODEL") or "llama3.2:3b").strip(), "config": {}}
    if gemini_api_key() and not openai_api_key():
        return {"provider": "gemini", "name": (os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI).strip(), "config": {}}
    return {"provider": "openai", "name": DEFAULT_OPENAI, "config": {}}


def _timeout_message(provider: str | None, model: str) -> str:
    return f"model call timed out ({registry.resolve_provider(provider)}/{model})"


def model_call_error_message(exc: Exception, provider: str | None = None) -> str | None:
    if isinstance(exc, ProviderError):
        return keys.redact(exc.message)
    text = keys.redact(str(exc))
    low = text.lower()
    name = type(exc).__name__
    pid = registry.resolve_provider(provider)
    if "missing credentials" in low or "api_key" in low:
        if pid == "gemini":
            return "Gemini API key is not configured. Add it in Settings > Providers."
        if pid == "ollama":
            return "Ollama is not configured. Set OLLAMA_BASE_URL in api/.env."
        return "OpenAI API key is not configured. Add it in Settings > Providers."
    if "429" in text or "insufficient" in low or "quota" in low or "credits" in low:
        if pid == "ollama":
            return "The local model server rejected the request (rate limit or overload). Retry in a moment or try a smaller Ollama model."
        if pid == "gemini":
            return "Gemini rejected the request (quota or rate limit). Check Google AI billing and limits."
        return (
            "OpenAI rejected the call because this account has no API credits left. "
            "Add credits in OpenAI billing, add a Gemini key in Settings, "
            "or set GATEWAY_MOCK=1 in api/.env for offline runs."
        )
    if name == "AuthenticationError" or "invalid api key" in low:
        if pid == "gemini":
            return "Gemini rejected the API key. Update it in Settings > Providers."
        if pid == "ollama":
            return "Ollama rejected the API key. Check OLLAMA_API_KEY in api/.env."
        return "OpenAI rejected the API key. Update it in Settings > Providers."
    if pid == "ollama" and (name in ("APIConnectionError", "APITimeoutError") or "connection" in low):
        return "Could not reach Ollama. Run `ollama serve` and check OLLAMA_BASE_URL in api/.env."
    if pid == "gemini" and (name in ("APIConnectionError", "APITimeoutError") or "connection" in low):
        return "Could not reach Gemini. Check network access and the key in Settings > Providers."
    if name in ("APIConnectionError", "APITimeoutError") or "connection error" in low:
        return "Could not reach the model API. Check network access and provider keys in Settings."
    return None


def cost_usd(model: str, usage: dict, response=None) -> float:
    if _mocked() and response is None:
        return mock_turns.usd(usage)
    try:
        import litellm

        kwargs: dict = {"model": model}
        if response is not None:
            kwargs["completion_response"] = response
        else:
            kwargs["prompt_tokens"] = usage.get("input_tokens") or 0
            kwargs["completion_tokens"] = usage.get("output_tokens") or 0
        value = litellm.completion_cost(**kwargs)
        return round(float(value or 0), 6)
    except Exception:
        return mock_turns.usd(usage)


def record_turn_cost(run: dict, usd: float) -> None:
    if usd <= 0:
        return
    from store import db

    agent_id = run.get("agentId")
    if not agent_id:
        return
    row = db.get("agent-spend", agent_id) or {"id": agent_id, "usd": 0.0, "calls": 0}
    row["usd"] = round(float(row.get("usd") or 0) + usd, 6)
    row["calls"] = int(row.get("calls") or 0) + 1
    db.put("agent-spend", agent_id, row)
    agent = db.get("agent", agent_id) or {}
    role = agent.get("roleKey")
    if not role:
        return
    role_row = db.get("role-spend", role) or {"id": role, "roleId": role, "usd": 0.0, "calls": 0}
    role_row["usd"] = round(float(role_row.get("usd") or 0) + usd, 6)
    role_row["calls"] = int(role_row.get("calls") or 0) + 1
    db.put("role-spend", role, role_row)


def supports_tool_calling(provider: str | None, name: str) -> bool:
    if _mocked():
        return True
    try:
        import litellm

        check = getattr(litellm, "supports_function_calling", None)
        if check is None:
            from litellm.utils import supports_function_calling as check
        return bool(check(model=routed_model(provider, name), custom_llm_provider=litellm_prefix(provider)))
    except Exception:
        return False


def list_live_models(provider: str | None) -> list[str]:
    pid = registry.resolve_provider(provider)
    if _mocked():
        return registry.get(pid).list_models()
    import litellm

    key = resolve_api_key(pid)
    prefix = litellm_prefix(pid)
    try:
        raw = litellm.get_valid_models(custom_llm_provider=prefix, api_key=key) or []
    except Exception:
        raw = []
    from app.models_catalog import is_chat

    names: list[str] = []
    for item in raw:
        name = str(item).split("/")[-1]
        if not name or not is_chat(name):
            continue
        if supports_tool_calling(pid, name):
            names.append(name)
    return sorted(set(names))


def list_model_ids(provider: str | None = None) -> list[str]:
    if _mocked():
        return registry.get(provider).list_models()
    return list_live_models(provider)


def test_connection(provider: str | None) -> None:
    pid = registry.resolve_provider(provider)
    if _mocked():
        return
    if not resolve_api_key(pid):
        raise ProviderError("No API key saved for this provider.")
    ids = list_live_models(pid)
    if not ids:
        raise ProviderError("Connected, but no tool-calling models were returned.")


def _litellm_kwargs(
    provider: str,
    model: str,
    messages: list,
    tools: list,
    config: dict,
    stream: bool,
    tool_choice: str | None,
) -> dict:
    import litellm

    litellm.drop_params = True
    litellm.suppress_debug_info = True
    kwargs: dict = {
        "model": routed_model(provider, model),
        "messages": messages,
        "stream": stream,
        "api_key": resolve_api_key(provider),
    }
    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    if config.get("temperature") is not None:
        kwargs["temperature"] = config["temperature"]
    if config.get("maxOutputTokens") is not None:
        kwargs["max_tokens"] = config["maxOutputTokens"]
    if stream:
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs


def _tool_calls_from_message(message) -> list[dict]:
    calls = []
    for tool in getattr(message, "tool_calls", None) or []:
        fn = getattr(tool, "function", None)
        calls.append(
            {
                "id": getattr(tool, "id", "") or "",
                "name": getattr(fn, "name", "") if fn else "",
                "arguments": getattr(fn, "arguments", "") if fn else "",
            }
        )
    return calls


def _from_response(response, model: str) -> dict:
    choice = response.choices[0]
    message = choice.message
    usage_obj = getattr(response, "usage", None)
    usage = {
        "input_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
    }
    return {
        "kind": "done",
        "content": getattr(message, "content", None) or "",
        "tool_calls": _tool_calls_from_message(message),
        "usage": usage,
        "usd": cost_usd(model, usage, response),
    }


def _from_chunks(chunks, model: str):
    pieces: list[str] = []
    calls: dict[int, dict] = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    last = None
    for chunk in chunks:
        last = chunk
        usage_obj = getattr(chunk, "usage", None)
        if usage_obj:
            usage = {
                "input_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
                "output_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
            }
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        if delta and getattr(delta, "content", None):
            pieces.append(delta.content)
            yield {"kind": "delta", "text": delta.content}
        for tool in (getattr(delta, "tool_calls", None) or []) if delta else []:
            slot = calls.setdefault(getattr(tool, "index", 0) or 0, {"id": "", "name": "", "arguments": ""})
            if getattr(tool, "id", None):
                slot["id"] = tool.id
            fn = getattr(tool, "function", None)
            if fn and getattr(fn, "name", None):
                slot["name"] = fn.name
            if fn and getattr(fn, "arguments", None):
                slot["arguments"] += fn.arguments
    yield {
        "kind": "done",
        "content": "".join(pieces),
        "tool_calls": [calls[index] for index in sorted(calls)],
        "usage": usage,
        "usd": cost_usd(model, usage, last),
    }


def iter_live_events(
    provider: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    config: dict,
    *,
    stream: bool = True,
    tool_choice: str | None = None,
):
    """LiteLLM-backed turn. Takes a model, messages, tools — not a role."""
    import litellm
    from litellm.exceptions import APIConnectionError, APIError, AuthenticationError, RateLimitError, Timeout

    kwargs = _litellm_kwargs(provider, model, messages, tools, config, stream, tool_choice)
    try:
        response = litellm.completion(**kwargs)
    except Timeout as exc:
        raise ModelTimeout(_timeout_message(provider, model)) from exc
    except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as exc:
        message = model_call_error_message(exc, provider) or keys.redact(str(exc))
        raise ProviderError(message) from exc
    except Exception as exc:
        message = model_call_error_message(exc, provider) or keys.redact(str(exc))
        raise ProviderError(message) from exc
    routed = kwargs["model"]
    if stream:
        yield from _from_chunks(response, routed)
        return
    yield _from_response(response, routed)


def _provider_stream(provider: str | None, model: str, messages, tools, config, stream: bool, tool_choice: str | None):
    impl = registry.get(provider)
    if _mocked():
        yield from impl.complete(model, messages, tools, config, stream=stream, tool_choice=tool_choice)
        return
    yield from iter_live_events(impl.id, model, messages, tools, config, stream=stream, tool_choice=tool_choice)


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
    tools: list[dict] | None = None,
    config: dict | None = None,
    *,
    run_id: str | None = None,
    call_index: int = 0,
    provider: str | None = None,
) -> dict:
    from gateway.request_capture import record
    from gateway.tool_pairing import assert_chat_tool_pairing

    tools = tools or []
    config = config or {}
    assert_chat_tool_pairing(messages)
    request_payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "config": config,
        "provider": registry.resolve_provider(provider),
    }
    turn: dict | None = None
    last: Exception | None = None
    for attempt in range(3):
        try:
            for event in _provider_stream(provider, model, messages, tools, config, False, None):
                if event.get("kind") == "done":
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
    turn["usd"] = cost_usd(routed_model(provider, model), turn.get("usage") or {})
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

    request_payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "config": config,
        "provider": registry.resolve_provider(provider),
    }

    def factory():
        yield from _provider_stream(provider, model, messages, tools, config, True, tool_choice)

    done_payload = None
    for event in _with_retries(model, provider, factory):
        if event["kind"] in ("retry", "thinking"):
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
            event["usd"] = cost_usd(routed_model(provider, model), event.get("usage") or {})
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
    if _mocked():
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
