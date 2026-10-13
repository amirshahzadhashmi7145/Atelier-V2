"""OpenAI calls live here and nowhere else."""

import json
import os
import threading
import time

# Tests push scripted turns here. Each turn is a dict with content, tool_calls, usage.
SCRIPTS: list[dict] = []
# Mock turns record the prompt they saw so tests can check a nudge landed.
PROMPTS: list[list] = []

# ponytail: the models list has no context window or price
PRICE_IN = 2.5
PRICE_OUT = 10.0


class ModelTimeout(Exception):
    pass

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
        if os.environ.get("MOCK_MODEL_HANG") == "1":
            limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or "60")
            time.sleep(limit + 0.05)
            raise ModelTimeout("Model call timed out waiting for the first token.")
        PROMPTS.append(messages)
        turn = _next_mock(messages)
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        pace = int(os.environ.get("STREAM_PACE_MS") or "0") / 1000
        if turn.get("deltas"):
            for piece in turn["deltas"]:
                yield {"kind": "delta", "text": piece["text"], "call": piece["call"], "index": piece["index"]}
                if pace:
                    time.sleep(pace)
            yield {"kind": "done", "content": turn.get("content") or "", "tool_calls": turn.get("tool_calls") or [], "usage": usage, "usd": usd(usage)}
            return
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
    if "interleave-bubbles" in blob:
        return [
            {
                "content": "First bubble.",
                "deltas": [
                    {"call": "a", "index": 2, "text": "bubble."},
                    {"call": "b", "index": 1, "text": "Second "},
                    {"call": "a", "index": 1, "text": "First "},
                    {"call": "b", "index": 2, "text": "bubble."},
                ],
                "tool_calls": [
                    {
                        "id": "call_done",
                        "name": "complete",
                        "arguments": {
                            "summary": {
                                "description": "Two bubbles.",
                                "filesChanged": [],
                                "dependencies": [],
                                "criteria": [],
                                "assumptions": [],
                                "followUps": [],
                            }
                        },
                    }
                ],
            }
        ]
    if "slow-command" in blob:
        return [
            {"content": "On it.", "tool_calls": [{"id": "call_slow", "name": "shell", "arguments": {"command": "sleep 8"}}]},
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_done",
                        "name": "complete",
                        "arguments": {
                            "summary": {
                                "description": "Command finished.",
                                "filesChanged": [],
                                "dependencies": [],
                                "criteria": [],
                                "assumptions": [],
                                "followUps": [],
                            }
                        },
                    }
                ],
            },
        ]
    if "tic tac toe" in blob.lower() and "ui" in blob.lower():
        html = "<!doctype html><title>Tic Tac Toe</title><h1>Tic Tac Toe</h1><div id=\"board\"></div>"
        package = json.dumps({"name": "tic-tac-toe", "private": True, "scripts": {"build": "node -e \"process.exit(0)\"", "test": "node -e \"process.exit(0)\""}})
        summary = {"description": "Tic Tac Toe UI.", "filesChanged": ["index.html", "package.json"], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}
        return [
            {
                "content": "Building the tic tac toe UI.",
                "tool_calls": [
                    {"id": "html", "name": "files", "arguments": {"op": "write", "path": "index.html", "content": html}},
                    {"id": "pkg", "name": "files", "arguments": {"op": "write", "path": "package.json", "content": package}},
                ],
            },
            {"content": "", "tool_calls": [{"id": "build", "name": "build_test", "arguments": {}}]},
            {"content": "", "tool_calls": [{"id": "shot", "name": "headless_browser", "arguments": {"url": "index.html"}}]},
            {"content": "", "tool_calls": [{"id": "done", "name": "complete", "arguments": {"summary": summary}}]},
        ]
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
