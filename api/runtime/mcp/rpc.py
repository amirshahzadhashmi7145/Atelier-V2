"""JSON-RPC surface for the studio MCP server."""

from __future__ import annotations

from runtime.mcp import handler, tokens

PROTOCOL = "2024-11-05"


def handle(body: dict, raw_token: str | None) -> tuple[int, dict]:
    row = tokens.validate(raw_token)
    if row is None:
        return 401, {"error": {"code": "unauthorized", "message": "MCP token is missing, wrong, or expired"}}
    from store import db

    run = db.get("run", row.get("runId") or "")
    if run is None:
        return 401, {"error": {"code": "unauthorized", "message": "MCP token is missing, wrong, or expired"}}
    method = body.get("method") or ""
    req_id = body.get("id")
    if method == "initialize":
        return 200, _ok(req_id, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": {"name": "atelier", "version": "18"}})
    if method in ("notifications/initialized", "initialized"):
        return 200, {"jsonrpc": "2.0"}
    if method == "ping":
        return 200, _ok(req_id, {})
    if method == "tools/list":
        return 200, _ok(req_id, {"tools": handler.list_tools()})
    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        result = handler.invoke(run, name, arguments if isinstance(arguments, dict) else {})
        text = result.get("output") if isinstance(result.get("output"), str) else str(result)
        if result.get("refused"):
            text = result.get("reason") or text
        return 200, _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": bool(result.get("refused")), "structuredContent": result})
    return 200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method {method}"}}


def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def token_from_headers(headers: dict) -> str | None:
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return headers.get("x-atelier-mcp-token") or headers.get("X-Atelier-Mcp-Token")
