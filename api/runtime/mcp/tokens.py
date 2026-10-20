"""Short-lived tokens bound to one OpenHands run. Never log the raw value."""

from __future__ import annotations

import hashlib
import secrets
import time

from store import db

PREFIX = "atk_"
TTL_SEC = 4 * 3600


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(run_id: str, ttl_sec: int = TTL_SEC) -> str:
    raw = PREFIX + secrets.token_urlsafe(24)
    db.put(
        "mcp-token",
        run_id,
        {
            "id": run_id,
            "runId": run_id,
            "hash": _hash(raw),
            "revoked": False,
            "expiresAt": time.time() + max(30, ttl_sec),
        },
    )
    return raw


def revoke(run_id: str) -> None:
    row = db.get("mcp-token", run_id)
    if not row:
        return
    row["revoked"] = True
    db.put("mcp-token", run_id, row)


def validate(raw: str | None) -> dict | None:
    token = (raw or "").strip()
    if not token.startswith(PREFIX):
        return None
    digest = _hash(token)
    now = time.time()
    for row in db.listing("mcp-token"):
        if row.get("hash") != digest:
            continue
        if row.get("revoked"):
            return None
        if float(row.get("expiresAt") or 0) < now:
            return None
        return row
    return None
