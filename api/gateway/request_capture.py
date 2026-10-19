"""Optional per-run model request/response capture with secret redaction."""

from __future__ import annotations

import json
import re
from pathlib import Path

from store import db

ROOT = Path(__file__).resolve().parents[1]
DEBUG_ROOT = ROOT / "debug" / "runs"

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s\"']+", re.I),
)


def _redact(value):
    if isinstance(value, str):
        from gateway import keys

        text = keys.redact(value)
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub(lambda m: m.group(0)[:8] + "…redacted", text)
        return text
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def should_record() -> bool:
    settings = db.get("settings", "runs") or {}
    return bool(settings.get("recordModelRequests"))


def record(run_id: str | None, call_index: int, payload: dict) -> None:
    if not run_id or not should_record():
        return
    folder = DEBUG_ROOT / run_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{call_index}.json"
    path.write_text(json.dumps(_redact(payload), indent=2), encoding="utf-8")


def capture_dir(run_id: str) -> Path | None:
    if not should_record():
        return None
    folder = DEBUG_ROOT / run_id
    return folder if folder.is_dir() else None
