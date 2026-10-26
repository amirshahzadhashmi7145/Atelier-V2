"""Regression tests for the security/reliability hardening in commit 12244d6
and its follow-up fixes (subprocess env isolation, browser SSRF, OpenHands event
dedup, run cancellation)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from runtime.sandbox import safe_subprocess_env
from runtime.tools import _safe_browser_target
from store import db

from test_engine import client, fresh  # noqa: F401


def test_safe_subprocess_env_strips_secrets_keeps_path(monkeypatch):
    # Stripping is by key name, so the values are deliberately innocuous (the
    # secret scanner must not flag this test file).
    monkeypatch.setenv("OPENAI_API_KEY", "value-a")
    monkeypatch.setenv("GEMINI_API_KEY", "value-b")
    monkeypatch.setenv("GITHUB_TOKEN", "value-c")
    monkeypatch.setenv("SOME_SECRET", "value-d")
    monkeypatch.setenv("DB_PASSWORD", "value-e")
    env = safe_subprocess_env()
    for leaked in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN", "SOME_SECRET", "DB_PASSWORD"):
        assert leaked not in env, leaked
    # The shell still needs these to run npm/node.
    assert "PATH" in env
    assert env["CI"] == "1"


def test_browser_target_rejects_file_and_internal_hosts():
    folder = Path(tempfile.mkdtemp())
    (folder / "page.html").write_text("<h1>ok</h1>")
    blocked = [
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://2852039166/",  # same address, decimal-encoded
        "http://10.0.0.5/",  # private
        "http://3232235777/",  # 192.168.0.1 decimal
        "http://[fd00::1]/",  # IPv6 private
        "../../../etc/passwd",  # path traversal out of the project
        "/etc/passwd",  # absolute path
    ]
    for url in blocked:
        assert _safe_browser_target(folder, url) is None, url


def test_browser_target_allows_loopback_relative_and_public():
    folder = Path(tempfile.mkdtemp())
    (folder / "page.html").write_text("<h1>ok</h1>")
    assert _safe_browser_target(folder, "http://127.0.0.1:5173/") == "http://127.0.0.1:5173/"
    assert _safe_browser_target(folder, "http://[::1]/") == "http://[::1]/"
    assert _safe_browser_target(folder, "https://example.com/") == "https://example.com/"
    assert _safe_browser_target(folder, "page.html") == (folder / "page.html").as_uri()


def test_import_skill_rejects_non_github_hosts(client: TestClient):
    for url in (
        "http://github.com.attacker.example/x",  # suffix trick
        "http://attacker.example/github.com/x",  # path, not host
        "http://169.254.169.254/x",
    ):
        res = client.post("/skills/import", json={"url": url})
        assert res.status_code == 422, url


def test_publish_oh_event_dedups_only_consecutive_identical_calls():
    from runtime.openhands.runner import _publish_oh_event

    db.put("run", "run_dedup", {"id": "run_dedup", "status": "running"})
    run = db.get("run", "run_dedup")
    state = {"n": 0, "lastCall": None}
    call = {"type": "TerminalAction", "command": "ls"}
    _publish_oh_event(run, call, state)
    _publish_oh_event(run, call, state)  # immediate duplicate -> dropped
    # A model-output between two identical calls breaks the run, so the next call is kept.
    _publish_oh_event(run, {"type": "message", "content": "thinking"}, state)
    _publish_oh_event(run, call, state)
    called = [e for e in db.events_for("run_dedup") if e["type"] == "TOOL_CALLED"]
    assert len(called) == 2


def test_cancel_run_is_safe_when_no_client_registered():
    from runtime.openhands.runner import cancel_run

    # No registered client for this id -> must be a no-op, never raise.
    cancel_run("run_never_started")


def test_ensure_not_cancelled_raises_for_cancelled_run():
    from runtime.openhands.runner import RunCancelled, _ensure_not_cancelled

    db.put("run", "run_cx", {"id": "run_cx", "status": "cancelled"})
    raised = False
    try:
        _ensure_not_cancelled("run_cx")
    except RunCancelled:
        raised = True
    assert raised
    # A running run does not raise.
    db.put("run", "run_cx2", {"id": "run_cx2", "status": "running"})
    _ensure_not_cancelled("run_cx2")


def test_append_event_sequence_is_monotonic_and_contiguous():
    db.put("run", "run_seq", {"id": "run_seq", "status": "running"})
    for _ in range(5):
        db.append_event("run_seq", "TOOL_CALLED", {"name": "x"})
    seqs = [e["seq"] for e in db.events_for("run_seq")]
    assert seqs == [1, 2, 3, 4, 5]
