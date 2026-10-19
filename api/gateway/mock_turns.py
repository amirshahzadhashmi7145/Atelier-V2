"""Scripted model turns for GATEWAY_MOCK=1 tests."""

from __future__ import annotations

import json
import re
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


def _done_turns(description: str, endpoints=None) -> list[dict]:
    summary = {
        "description": description,
        "filesChanged": [],
        "dependencies": [],
        "criteria": [],
        "assumptions": [],
        "followUps": [],
    }
    if endpoints:
        summary["endpoints"] = endpoints
    return [
        {
            "content": description,
            "tool_calls": [{"id": "done", "name": "complete", "arguments": {"summary": summary}}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    ]


def _lead_turns(blob: str) -> list[dict]:
    members = []
    for line in blob.splitlines():
        match = re.search(r"id=(\S+)\s+name=(.*?)\s+role=(\S+)(?:\s+kind=(\S+))?", line)
        if match:
            members.append(
                {
                    "id": match.group(1),
                    "name": match.group(2),
                    "role": match.group(3).lower(),
                    "kind": (match.group(4) or "worker").lower(),
                }
            )
    workers = [item for item in members if item["kind"] != "supervisor"]
    try:
        from store import db

        ranked = []
        for item in workers:
            role = db.get("role", item["role"])
            rank = 0 if role and role.get("contractFile") else 1
            ranked.append((rank, item, role))
        ranked.sort(key=lambda row: (row[0], row[1].get("name") or ""))
        workers = [row[1] for row in ranked]
        roles = {row[1]["id"]: row[2] for row in ranked}
    except Exception:
        roles = {}
    calls = []
    for index, item in enumerate(workers, start=1):
        role = roles.get(item["id"]) or {}
        contract = role.get("contractFile")
        if contract:
            text = f"Implement the HTTP API, database, and auth. Produce {contract}."
        else:
            text = "Build the React UI against the contract"
        calls.append(
            {
                "id": f"task_{index}",
                "name": "create_task",
                "arguments": {
                    "text": text,
                    "assignToAgentId": item["id"],
                    "acceptanceCriteria": ["criteria met"],
                    "order": index,
                },
            }
        )
    if not calls:
        return _done_turns("Need worker members before I can split the work.")
    calls.append({"id": "done", "name": "complete", "arguments": {"summary": {"description": "Plan ready."}}})
    return [{"content": "Splitting the work.", "tool_calls": calls, "usage": {"input_tokens": 1, "output_tokens": 1}}]


def _review_turns(blob: str) -> list[dict]:
    low = blob.lower()
    summary = ""
    if "Author summary:" in blob:
        summary = blob.split("Author summary:", 1)[1].splitlines()[0].lower()
    seeded = "omit delete" in low or "omits delete" in low
    delete_unmet = bool(re.search(r"\b(delete|remove)\b", low)) and not re.search(r"\b(delete|deleted|remove|removed)\b", summary)
    verdict = "changes_requested" if seeded or delete_unmet else "approve"
    notes = "The result omits delete." if verdict == "changes_requested" else "All criteria are met."
    return [
        {
            "content": notes,
            "tool_calls": [{"id": "rev", "name": "record_review", "arguments": {"verdict": verdict, "notes": notes}}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    ]


def _plan(messages: list[dict]) -> list[dict]:
    blob = "\n".join(item.get("content") or "" for item in messages if isinstance(item.get("content"), str))
    if "force-fail" in blob:
        return [{"content": "This will fail.", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 600_000}}]
    if "# Review packet" in blob:
        return _review_turns(blob)
    if "# Project members and scope" in blob:
        return _lead_turns(blob)
    if "omits delete" in blob.lower() or "omit delete" in blob.lower():
        return _done_turns("Notes can be listed and created.")
    if "Implement the HTTP API" in blob or "Produce api/CONTRACT.md" in blob:
        return _done_turns(
            "API ready.",
            endpoints=[{"method": "POST", "path": "/login", "request": "{email}", "response": "{token}"}],
        )
    if "Build the React UI" in blob or "Do: user interfaces" in blob:
        return _done_turns("UI against the contract.")
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
