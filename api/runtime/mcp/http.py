"""HTTP JSON-RPC endpoint for the studio MCP server."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from runtime.mcp import rpc

router = APIRouter()


@router.post("/mcp", include_in_schema=False)
async def mcp_http(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    status, payload = rpc.handle(body, rpc.token_from_headers(dict(request.headers)))
    return JSONResponse(payload, status_code=status)
