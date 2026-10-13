"""OpenAI calls live here and nowhere else."""

import json
import os
import threading
import time

# Tests push scripted turns here. Each turn is a dict with content, tool_calls, usage.
SCRIPTS: list[dict] = []

# ponytail: the models list has no context window or price
PRICE_IN = 2.5
PRICE_OUT = 10.0

_plans = threading.local()
_defaults = 0


def usd(usage: dict) -> float:
    return round((usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000, 6)


def begin() -> None:
    _plans.queue = None


def complete(model: str, messages: list[dict], tools: list[dict], config: dict) -> dict:
    if os.environ.get("GATEWAY_MOCK") == "1":
        turn = SCRIPTS.pop(0) if SCRIPTS else _default_turn()
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        return {**turn, "usage": usage, "usd": usd(usage)}
    from openai import OpenAI

    kwargs: dict = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    if "temperature" in config:
        kwargs["temperature"] = config["temperature"]
    if "maxOutputTokens" in config:
        kwargs["max_completion_tokens"] = config["maxOutputTokens"]
    response = OpenAI().chat.completions.create(**kwargs)
    choice = response.choices[0].message
    usage = {
        "input_tokens": response.usage.prompt_tokens if response.usage else 0,
        "output_tokens": response.usage.completion_tokens if response.usage else 0,
    }
    calls = []
    for call in choice.tool_calls or []:
        calls.append({"id": call.id, "name": call.function.name, "arguments": call.function.arguments})
    return {"content": choice.content or "", "tool_calls": calls, "usage": usage, "usd": usd(usage)}


def stream_turn(model: str, messages: list[dict], tools: list[dict], config: dict):
    if os.environ.get("GATEWAY_MOCK") == "1":
        turn = _next_mock(messages)
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        pace = int(os.environ.get("STREAM_PACE_MS") or "0") / 1000
        text = turn.get("content") or ""
        words = text.split(" ")
        for index, word in enumerate(words):
            if word == "":
                continue
            piece = word if index == len(words) - 1 else word + " "
            yield {"kind": "delta", "text": piece}
            if pace:
                time.sleep(pace)
        yield {"kind": "done", "content": text, "tool_calls": turn.get("tool_calls") or [], "usage": usage, "usd": usd(usage)}
        return
    from openai import OpenAI

    kwargs: dict = {"model": model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
    if tools:
        kwargs["tools"] = tools
    if "temperature" in config:
        kwargs["temperature"] = config["temperature"]
    if "maxOutputTokens" in config:
        kwargs["max_completion_tokens"] = config["maxOutputTokens"]
    pieces: list[str] = []
    calls: dict[int, dict] = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    for chunk in OpenAI().chat.completions.create(**kwargs):
        if getattr(chunk, "usage", None):
            usage = {"input_tokens": chunk.usage.prompt_tokens or 0, "output_tokens": chunk.usage.completion_tokens or 0}
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            pieces.append(delta.content)
            yield {"kind": "delta", "text": delta.content}
        for tool in (delta.tool_calls or []) if delta else []:
            slot = calls.setdefault(tool.index or 0, {"id": "", "name": "", "arguments": ""})
            if tool.id:
                slot["id"] = tool.id
            if tool.function and tool.function.name:
                slot["name"] = tool.function.name
            if tool.function and tool.function.arguments:
                slot["arguments"] += tool.function.arguments
    yield {
        "kind": "done",
        "content": "".join(pieces),
        "tool_calls": [calls[index] for index in sorted(calls)],
        "usage": usage,
        "usd": usd(usage),
    }


def summarize(model: str, previous: str, older: str) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        line = older.strip().splitlines()[-1] if older.strip() else "nothing yet"
        return f"Earlier: {line}"[:500]
    turn = complete(
        model,
        [{"role": "user", "content": "Summarise the older conversation in one short paragraph.\n" + previous + "\n" + older}],
        [],
        {},
    )
    return turn.get("content") or previous or "Earlier conversation."


def list_model_ids() -> list[str]:
    if os.environ.get("GATEWAY_MOCK") == "1":
        return ["gpt-5", "gpt-4.1", "gpt-4.1-mini"]
    from openai import OpenAI

    return [item.id for item in OpenAI().models.list()]


def _next_mock(messages: list[dict]) -> dict:
    if SCRIPTS:
        return SCRIPTS.pop(0)
    queue = getattr(_plans, "queue", None)
    if not queue:
        queue = _plan(messages)
        _plans.queue = queue
    turn = queue.pop(0)
    if not queue:
        _plans.queue = None
    return turn


def _plan(messages: list[dict]) -> list[dict]:
    blob = "\n".join(item.get("content") or "" for item in messages if isinstance(item.get("content"), str))
    if "force-fail" in blob:
        return [{"content": "This will fail.", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600_000}}]
    rule = ""
    for line in blob.splitlines():
        if line.lower().startswith("pass rule:"):
            rule = line.split(":", 1)[1].strip()
    criteria = []
    if "Criteria:" in blob:
        criteria = [line.strip() for line in blob.split("Criteria:", 1)[1].splitlines() if line.strip()]
    page = "<h1>Hero</h1><section>One</section><section>Two</section><section>Three</section>"
    turns = [
        {
            "content": "Building the page now.",
            "tool_calls": [{"id": "call_write", "name": "files", "arguments": {"op": "write", "path": "index.html", "content": page}}],
        }
    ]
    build = rule in ("build_and_tests", "build_tests_and_screenshots") or "build" in rule.lower()
    shots = rule == "build_tests_and_screenshots" or "screenshot" in rule.lower()
    if build:
        package = json.dumps({"name": "eval", "private": True, "scripts": {"build": "node -e 'process.exit(0)'", "test": "node -e 'process.exit(0)'"}})
        turns.append({"content": "", "tool_calls": [{"id": "call_pkg", "name": "files", "arguments": {"op": "write", "path": "package.json", "content": package}}]})
        turns.append({"content": "", "tool_calls": [{"id": "call_build", "name": "build_test", "arguments": {}}]})
    if shots:
        turns.append({"content": "", "tool_calls": [{"id": "call_shot", "name": "headless_browser", "arguments": {"url": ""}}]})
    turns.append(
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_done",
                    "name": "complete",
                    "arguments": {
                        "summary": {
                            "description": "Landing page with a hero and three feature cards.",
                            "filesChanged": ["index.html"],
                            "dependencies": [],
                            "criteria": [{"text": text, "evidence": "shown in the build"} for text in criteria],
                            "assumptions": [],
                            "followUps": [],
                        }
                    },
                }
            ],
        }
    )
    return turns


def _default_turn() -> dict:
    global _defaults
    _defaults += 1
    return _plan([{"role": "user", "content": ""}])[1 if _defaults > 1 else 0]
