"""Host-side stdio MCP process spawned by OpenHands. Token arrives in env, never argv."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _read_message() -> dict | None:
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk
    length = 0
    for line in header.decode("utf-8", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip() or 0)
    raw = sys.stdin.buffer.read(length) if length else b""
    if not raw:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        raw = line
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


def _write_message(payload: dict) -> None:
    blob = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(blob)}\r\n\r\n".encode("ascii") + blob)
    sys.stdout.buffer.flush()


def main() -> int:
    token = os.environ.get("ATELIER_MCP_TOKEN")
    from runtime.mcp import rpc

    while True:
        body = _read_message()
        if body is None:
            return 0
        _status, payload = rpc.handle(body, token)
        if body.get("id") is not None or payload.get("error"):
            _write_message(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
