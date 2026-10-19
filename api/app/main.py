import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import router
from runtime.mcp.http import router as mcp_router
from store import db

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Agent Studio")

origins = os.environ.get(
    "CORS_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3001,http://localhost:3001",
).split(",")
allowed_origins = [item.strip() for item in origins if item.strip()]


@app.exception_handler(Exception)
async def unhandled_error(request: Request, _exc: Exception):
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin and origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        {"code": "internal", "message": "Internal server error"},
        status_code=500,
        headers=headers,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)
app.include_router(router)
app.include_router(mcp_router)


def _bootstrap_gemini() -> None:
    from app import models_catalog
    from gateway import openai_gateway

    if openai_gateway.gemini_api_key() and os.environ.get("OLLAMA_BASE_URL", "").strip():
        return
    if not openai_gateway.gemini_api_key():
        return
    cached = db.get("model-cache", "gemini")
    if not cached or not cached.get("ids"):
        try:
            ids = [name for name in openai_gateway.list_model_ids("gemini") if models_catalog.is_chat(name)]
            if ids:
                db.put("model-cache", "gemini", {"ids": ids})
                provider = db.get("provider", "gemini") or {"id": "gemini", "name": "Google Gemini"}
                provider["connected"] = True
                provider["keyRef"] = "env:GEMINI_API_KEY"
                provider["modelsCachedAt"] = db.now()
                db.put("provider", "gemini", provider)
        except Exception:
            pass
    if db.get("meta", "gemini_agents"):
        return
    spec = openai_gateway.default_model_spec()
    if spec.get("provider") != "gemini":
        return
    for agent in db.listing("agent"):
        agent["model"] = {**spec, "config": (agent.get("model") or {}).get("config") or {}}
        agent["updatedAt"] = db.now()
        db.put("agent", agent["id"], agent)
    db.put("meta", "gemini_agents", {"ok": True})


@app.on_event("startup")
def startup() -> None:
    db.engine()
    _bootstrap_gemini()
