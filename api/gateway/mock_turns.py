"""Scripted model turns for GATEWAY_MOCK=1 tests."""

from __future__ import annotations

import json
import threading

SCRIPTS: list[dict] = []
PROMPTS: list[list] = []

PRICE_IN = 2.5
PRICE_OUT = 10.0

_plans = threading.local()
_defaults = 0


def usd(usage: dict) -> float:
    return round((usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000, 6)


def next_mock(messages: list[dict]) -> dict:
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
        html = '<!doctype html><title>Tic Tac Toe</title><h1>Tic Tac Toe</h1><div id="board"></div>'
        package = json.dumps(
            {"name": "tic-tac-toe", "private": True, "scripts": {"build": "node -e \"process.exit(0)\"", "test": "node -e \"process.exit(0)\""}}
        )
        summary = {
            "description": "Tic Tac Toe UI.",
            "filesChanged": ["index.html", "package.json"],
            "dependencies": [],
            "criteria": [],
            "assumptions": [],
            "followUps": [],
        }
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


def default_turn() -> dict:
    global _defaults
    _defaults += 1
    return _plan([{"role": "user", "content": ""}])[1 if _defaults > 1 else 0]
