import json
import os
import queue
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app import bridge, models_catalog
from gateway import keys
from gateway.exceptions import ProviderError
from gateway.llm import default_model_spec, env_var_for, has_api_key, list_model_ids, missing_key_message, test_connection
from store import db

router = APIRouter()


def error(status: int, code: str, message: str, details: dict | None = None):
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(body, status_code=status)


def missing():
    return error(404, "not_found", "Not found")


@router.get("/agents")
def list_agents():
    return db.listing("agent")


@router.post("/agents", status_code=201)
def create_agent(body: dict):
    if not body.get("name") or not body.get("roleKey"):
        return error(422, "invalid", "name and roleKey are required")
    created = _agent(body)
    db.put("agent", created["id"], created)
    return created


@router.get("/agents/{id}")
def get_agent(id: str):
    return db.get("agent", id) or missing()


@router.patch("/agents/{id}")
def patch_agent(id: str, body: dict):
    agent = db.get("agent", id)
    if agent is None:
        return missing()
    for key in ("name", "roleKey", "description", "model", "backupModel", "toolIds", "skillIds", "stackIds", "zones", "scope", "reportsTo", "capabilities", "workerEngine"):
        if key == "workerEngine":
            agent["workerEngine"] = "openhands"
            continue
        if key in body:
            agent[key] = models_catalog.normalize_spec(body[key]) if key in ("model", "backupModel") else body[key]
    agent["updatedAt"] = db.now()
    db.put("agent", id, agent)
    return agent


@router.delete("/agents/{id}", status_code=204)
def delete_agent(id: str):
    if db.get("agent", id) is None:
        return missing()
    db.delete("agent", id)
    return JSONResponse(status_code=204, content=None)


@router.get("/agents/{id}/versions")
def list_versions(id: str):
    if db.get("agent", id) is None:
        return missing()
    rows = [item for item in db.listing("version") if item["agentId"] == id]
    rows.sort(key=lambda item: item["version"])
    return rows


@router.post("/agents/{id}/versions", status_code=201)
def create_version(id: str, body: dict):
    agent = db.get("agent", id)
    if agent is None:
        return missing()
    return _save_version(agent, body.get("sections") or agent.get("sections") or {})


@router.post("/agents/{id}/versions/{v}/activate")
def activate(id: str, v: int):
    agent = db.get("agent", id)
    version = _version(id, v)
    if agent is None or version is None:
        return missing()
    pending = [item for item in version["evalResults"] if item["status"] != "pass"]
    if pending:
        return error(409, "evals_required", "Every eval on this version must pass before it can be active")
    agent["activePromptVersionId"] = version["id"]
    agent["updatedAt"] = db.now()
    db.put("agent", id, agent)
    return agent


@router.get("/agents/{id}/versions/{v}/diff")
def diff_versions(id: str, v: int, against: int):
    current = _version(id, v)
    previous = _version(id, against)
    if current is None or previous is None:
        return missing()
    sections = []
    for name in ("role", "goal", "instructions", "constraints", "output"):
        sections.append({"path": name, "before": previous["sections"].get(name, ""), "after": current["sections"].get(name, "")})
    return {"againstVersion": against, "sections": sections}


@router.get("/roles")
def list_roles():
    from runtime import roles as rolelib

    rolelib.sync_roles()
    rows = db.listing("role")
    rows.sort(key=lambda item: (item.get("layer") or 0, item.get("name") or item["id"]))
    return rows


@router.post("/roles", status_code=201)
def create_role(body: dict):
    from runtime import roles as rolelib

    try:
        role = rolelib.normalize(body)
    except ValueError as exc:
        return error(422, "invalid", str(exc))
    if db.get("role", role["id"]):
        return error(409, "exists", "A role with that id already exists")
    db.put("role", role["id"], role)
    return role


@router.get("/roles/{id}")
def get_role(id: str):
    return db.get("role", id) or missing()


@router.patch("/roles/{id}")
def patch_role(id: str, body: dict):
    from runtime import roles as rolelib

    existing = db.get("role", id)
    if existing is None:
        return missing()
    try:
        role = rolelib.normalize({**body, "id": id}, existing)
    except ValueError as exc:
        return error(422, "invalid", str(exc))
    db.put("role", id, role)
    return role


@router.post("/roles/{id}/reset")
def reset_role(id: str):
    from runtime import roles as rolelib

    if not rolelib.is_seed(id):
        return missing()
    if db.get("role", id) is None:
        return missing()
    return rolelib.reset_seed(id)


@router.delete("/roles/{id}", status_code=204)
def delete_role(id: str):
    if db.get("role", id) is None:
        return missing()
    db.delete("role", id)
    return JSONResponse(status_code=204, content=None)


@router.get("/roles/{id}/lessons")
def list_lessons(id: str):
    from runtime import lessons

    if db.get("role", id) is None:
        return missing()
    return lessons.for_role(id)


@router.delete("/roles/{id}/lessons/{lessonId}", status_code=204)
def delete_lesson(id: str, lessonId: str):
    from runtime import lessons

    if db.get("role", id) is None:
        return missing()
    if not lessons.delete(id, lessonId):
        return missing()
    return JSONResponse(status_code=204, content=None)


@router.get("/roles/{id}/suggestion")
def role_suggestion(id: str):
    from runtime import fit

    if db.get("role", id) is None:
        return missing()
    found = fit.suggestion(id)
    if found is None:
        return {"roleKey": id, "name": None, "provider": None, "reason": "not enough data yet", "tasks": 0}
    return found


@router.get("/projects/{id}/needs")
def list_needs(id: str):
    from runtime import needs

    if db.get("project", id) is None:
        return missing()
    return needs.listing(id)


@router.post("/needs/{id}/answer")
def answer_need(id: str, body: dict):
    from runtime import needs

    text = (body.get("text") or "").strip()
    if not text:
        return error(422, "invalid", "text is required")
    row = needs.resolve(id, text)
    if row is None:
        return missing()
    return row


@router.get("/tags")
def list_available_tags():
    from runtime import roles as rolelib

    rolelib.sync_roles()
    return {"tags": rolelib.tags_catalog()}


@router.post("/agents/{id}/compile-preview")
def compile_preview(id: str, body: dict):
    agent = db.get("agent", id)
    if agent is None:
        return missing()
    from runtime import roles as rolelib

    return bridge.compile_prompt(
        body.get("sections") or {},
        body.get("toolIds") or [],
        body.get("skillIds") or [],
        body.get("stackIds") or [],
        scope=body.get("scope"),
        worker=not rolelib.is_supervisor(agent),
    )


@router.post("/agents/{id}/evals", status_code=201)
def create_eval(id: str, body: dict):
    agent = db.get("agent", id)
    if agent is None:
        return missing()
    item = {"id": db.nid("eval"), "name": body["name"], "task": body["task"], "criteria": body["criteria"], "passRule": body["passRule"]}
    agent["evals"] = [*agent.get("evals", []), item]
    db.put("agent", id, agent)
    return item


@router.delete("/agents/{id}/evals/{evalId}", status_code=204)
def delete_eval(id: str, evalId: str):
    agent = db.get("agent", id)
    if agent is None:
        return missing()
    agent["evals"] = [item for item in agent.get("evals", []) if item["id"] != evalId]
    db.put("agent", id, agent)
    return JSONResponse(status_code=204, content=None)


@router.post("/agents/{id}/versions/{v}/evals/run")
def run_evals(id: str, v: int):
    agent = db.get("agent", id)
    version = _version(id, v)
    if agent is None or version is None:
        return missing()
    if not agent.get("evals"):
        return error(422, "no_evals", "Add an eval first")
    return bridge.run_evals(agent, version)


@router.post("/agents/{id}/versions/{v}/evals/compare")
def compare_evals(id: str, v: int, body: dict):
    agent = db.get("agent", id)
    version = _version(id, v)
    if agent is None or version is None:
        return missing()
    models = body.get("models") or []
    if not models or not agent.get("evals"):
        return error(422, "no_evals", "Choose models and add an eval first")
    return bridge.compare_evals(agent, version, models)


@router.get("/tools")
def list_tools():
    return [item for item in db.listing("tool") if item["kind"] != "control"]


@router.post("/tools", status_code=201)
def create_tool(body: dict):
    for key in ("kind", "name", "description", "schema", "permission"):
        if key not in body:
            return error(422, "invalid", "kind, name, description, schema, and permission are required")
    created = {"id": db.nid("tool"), "config": {}, "source": body.get("source") or "user", "enabled": body.get("enabled", True), **body}
    db.put("tool", created["id"], created)
    return created


@router.patch("/tools/{id}")
def patch_tool(id: str, body: dict):
    tool = db.get("tool", id)
    if tool is None:
        return missing()
    tool.update({key: value for key, value in body.items() if key in ("name", "description", "schema", "permission", "config", "enabled")})
    db.put("tool", id, tool)
    return tool


@router.post("/tools/mcp/discover")
def discover_mcp(body: dict):
    if not body.get("serverUrl"):
        return error(400, "invalid", "serverUrl is required")
    schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    return {
        "tools": [
            {"name": "repo.search", "description": "Search the connected repository.", "schema": schema, "permission": "read"},
            {"name": "repo.read", "description": "Read a file from the connected repository.", "schema": schema, "permission": "read"},
            {"name": "repo.write", "description": "Write a file in the connected repository.", "schema": schema, "permission": "write"},
            {"name": "repo.web", "description": "Fetch a page from the web.", "schema": schema, "permission": "external"},
        ]
    }


@router.post("/tools/api/import")
def import_spec(body: dict):
    if not body.get("spec") and not body.get("specUrl"):
        return error(400, "invalid", "spec or specUrl is required")
    if not body.get("spec"):
        return error(422, "invalid", "Paste the spec to import operations")
    document = yaml.safe_load(body["spec"]) or {}
    operations = []
    for path, methods in (document.get("paths") or {}).items():
        for method, operation in (methods or {}).items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operationId": operation.get("operationId") or f"{method}_{path}",
                    "summary": operation.get("summary") or "",
                    "description": operation.get("description") or "",
                }
            )
    return {"operations": operations}


@router.get("/data-sources")
def list_sources():
    return db.listing("datasource")


@router.post("/data-sources", status_code=201)
def create_source(body: dict):
    created = {"id": db.nid("ds"), "lastPulledAt": None, "pagesChanged": None, "versionTag": None, **body}
    db.put("datasource", created["id"], created)
    return created


@router.post("/data-sources/{id}/refresh")
def refresh_source(id: str):
    source = db.get("datasource", id)
    if source is None:
        return missing()
    source["lastPulledAt"] = db.now()
    db.put("datasource", id, source)
    return source


@router.get("/skills")
def list_skills():
    return db.listing("skill")


@router.post("/skills", status_code=201)
def create_skill(body: dict):
    try:
        created = _skill(body)
    except ValueError as exc:
        return error(422, "invalid", str(exc))
    db.put("skill", created["id"], created)
    return created


@router.get("/skills/{id}")
def get_skill(id: str):
    return db.get("skill", id) or missing()


@router.patch("/skills/{id}")
def patch_skill(id: str, body: dict):
    skill = db.get("skill", id)
    if skill is None:
        return missing()
    skill.update({key: body[key] for key in ("name", "description", "body", "files") if key in body})
    try:
        _check_skill_size(skill.get("body") or "")
    except ValueError as exc:
        return error(422, "invalid", str(exc))
    skill["version"] += 1
    skill["versions"].append({"version": skill["version"], "createdAt": db.now()})
    db.put("skill", id, skill)
    return skill


@router.post("/skills/import", status_code=201)
def import_skill(body: dict):
    import httpx
    from urllib.parse import urlparse

    url = body.get("url") or ""
    host = (urlparse(url).hostname or "").lower()
    if host not in ("github.com", "www.github.com", "raw.githubusercontent.com"):
        return error(422, "invalid", "A github.com URL is required")
    raw = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    # No redirect following: the raw host serves the file directly, and a redirect
    # could otherwise send the fetch to an attacker-controlled host (SSRF).
    response = httpx.get(raw, timeout=15, follow_redirects=False)
    if response.status_code >= 300:
        return error(422, "invalid", "The skill URL did not respond")
    created = _skill({"name": body.get("name") or url.rstrip("/").split("/")[-1], "description": body.get("description") or url, "body": response.text, "origin": url})
    db.put("skill", created["id"], created)
    return created


@router.get("/stacks")
def list_stacks():
    return db.listing("stack")


@router.post("/stacks", status_code=201)
def create_stack(body: dict):
    created = {"id": db.nid("stack"), "enabledByDefault": True, "dataSourceIds": body.get("dataSourceIds") or [], "skillIds": body.get("skillIds") or [], **body}
    db.put("stack", created["id"], created)
    return created


@router.patch("/stacks/{id}")
def patch_stack(id: str, body: dict):
    stack = db.get("stack", id)
    if stack is None:
        return missing()
    stack.update({key: body[key] for key in ("name", "version", "packageAllowList", "skillIds", "dataSourceIds", "enabledByDefault") if key in body})
    db.put("stack", id, stack)
    return stack


def _models_from_caches() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for provider in db.listing("provider"):
        cached = db.get("model-cache", provider["id"])
        if cached and cached.get("ids"):
            rows.extend((name, provider["id"]) for name in cached["ids"])
            seen.add(provider["id"])
    for key in ("openai", "gemini", "ollama"):
        if key in seen:
            continue
        cached = db.get("model-cache", key)
        if cached and cached.get("ids"):
            rows.extend((name, key) for name in cached["ids"])
    return rows


@router.get("/models")
def list_models():
    saved = db.get("model-tags", "all") or {}
    rows = _models_from_caches()
    if not rows:
        cached = db.get("model-cache", "openai")
        rows = [(name, "openai") for name in (cached["ids"] if cached else [])]
    agents = db.listing("agent")
    runs = db.listing("run")
    models = []
    seen: set[str] = set()
    for name, cache_provider in rows:
        ident = models_catalog.model_id(name)
        if ident in seen or not models_catalog.is_chat(ident) or models_catalog.is_retired(ident):
            continue
        seen.add(ident)
        record = models_catalog.info(ident, cache_provider)
        record["ownStats"] = _stats(name, agents, runs)
        models.append(record)
    return models


@router.get("/model-tags")
def list_tags():
    saved = db.get("model-tags", "all") or {}
    cached = db.get("model-cache", "openai") or {"ids": []}
    result = {}
    for name in cached["ids"]:
        ident = models_catalog.model_id(name)
        if models_catalog.is_chat(ident) and not models_catalog.is_retired(ident):
            result[ident] = saved.get(ident) or saved.get(name) or models_catalog.seed_tags(ident)
    return result


@router.put("/model-tags")
def save_tag(body: dict):
    saved = db.get("model-tags", "all") or {}
    saved[body["name"]] = {"tags": body.get("tags") or [], "note": body.get("note") or "", "heuristic": False}
    db.put("model-tags", "all", saved)
    return saved[body["name"]]


@router.get("/settings/runs")
def get_run_settings():
    from runtime import lead as leadlib

    return leadlib.settings()


@router.put("/settings/runs")
def put_run_settings(body: dict):
    from runtime import lead as leadlib

    current = leadlib.settings()
    current.update(body)
    db.put("settings", "runs", current)
    return current


def _public_provider(row: dict) -> dict:
    pid = row["id"]
    env_name = env_var_for(pid)
    if not row.get("envVar"):
        row["envVar"] = env_name
        db.put("provider", pid, row)
    stored = keys.has(pid)
    env_val = keys.env_fallback(env_name)
    if pid == "gemini" and not env_val:
        env_val = keys.env_fallback("GOOGLE_API_KEY")
    mocked = os.environ.get("GATEWAY_MOCK") == "1"
    if stored:
        key_ref = f"secret:{pid}"
        hint = keys.hint(pid)
    elif env_val:
        key_ref = f"env:{env_name}" if env_name else "env"
        hint = keys.mask(env_val)
    elif mocked:
        key_ref = f"env:{env_name}" if env_name else None
        hint = None
    else:
        key_ref = None
        hint = None
    return {
        "id": pid,
        "name": row.get("name") or pid,
        "keyRef": key_ref,
        "keyHint": hint,
        "connected": bool(row.get("connected")) or mocked,
        "modelsCachedAt": row.get("modelsCachedAt"),
    }


@router.get("/providers")
def list_providers():
    return [_public_provider(row) for row in db.listing("provider")]


@router.put("/providers/{id}")
def put_provider(id: str, body: dict):
    provider = db.get("provider", id)
    if provider is None:
        return missing()
    api_key = body.get("apiKey")
    if not api_key or not str(api_key).strip():
        return error(422, "invalid", "apiKey is required")
    keys.save(id, str(api_key))
    provider["connected"] = False
    db.put("provider", id, provider)
    return _public_provider(provider)


@router.delete("/providers/{id}/key")
def delete_provider_key(id: str):
    provider = db.get("provider", id)
    if provider is None:
        return missing()
    keys.delete(id)
    provider["connected"] = False
    db.put("provider", id, provider)
    return _public_provider(provider)


@router.post("/providers/{id}/test")
def test_provider(id: str):
    provider = db.get("provider", id)
    if provider is None:
        return missing()
    try:
        test_connection(id)
    except ProviderError as exc:
        return error(422, "provider_error", keys.redact(str(exc)))
    provider["connected"] = True
    db.put("provider", id, provider)
    return _public_provider(provider)


@router.post("/providers/{id}/refresh")
def refresh_provider(id: str):
    if db.get("provider", id) is None:
        return missing()
    if os.environ.get("GATEWAY_MOCK") != "1" and not has_api_key(id):
        return error(422, "key_missing", "Add an API key in Settings > Providers")
    ids = [name for name in list_model_ids(id) if models_catalog.is_chat(name) and not models_catalog.is_retired(name)]
    db.put("model-cache", id, {"ids": ids})
    provider = db.get("provider", id)
    provider["connected"] = True
    provider["modelsCachedAt"] = db.now()
    db.put("provider", id, provider)
    return list_models()


@router.get("/role-fits")
def list_role_fits():
    return db.listing("role-fit")


@router.put("/role-fits/{roleId}")
def save_role_fit(roleId: str, body: dict):
    labels = body.get("labels") if isinstance(body.get("labels"), list) else []
    row = {"id": roleId, "roleId": roleId, "labels": [str(item) for item in labels]}
    db.put("role-fit", roleId, row)
    return row


@router.get("/library")
def list_library(kind: str):
    if kind not in ("agent", "skill", "stack"):
        return error(400, "invalid", "kind must be agent, skill, or stack")
    library = db.library()
    items = library["agents"] if kind == "agent" else library["skills"] if kind == "skill" else library["stacks"]
    return [
        {
            "id": item["id"],
            "kind": kind,
            "name": item["name"],
            "description": item.get("description") or f"{item['name']} {item.get('version', '')}".strip(),
        }
        for item in items
    ]


@router.post("/library/{id}/import", status_code=201)
def import_library(id: str):
    library = db.library()
    template = next((item for item in library["agents"] if item["id"] == id), None)
    if template:
        for skill_id in template["skillIds"]:
            _import_skill(library, skill_id)
        for stack_id in template["stackIds"]:
            _import_stack(library, stack_id)
        agent = _agent(template)
        agent["name"] = template["name"]
        agent["evals"] = template.get("evals") or []
        db.put("agent", agent["id"], agent)
        _save_version(agent, template["sections"])
        return {"kind": "agent", "id": agent["id"]}
    if any(item["id"] == id for item in library["skills"]):
        _import_skill(library, id)
        return {"kind": "skill", "id": id}
    if any(item["id"] == id for item in library["stacks"]):
        _import_stack(library, id)
        return {"kind": "stack", "id": id}
    return missing()


@router.get("/runs")
def list_runs(agentId: str | None = None, status: str | None = None, page: int = 1):
    rows = db.listing("run")
    if agentId:
        rows = [item for item in rows if item["agentId"] == agentId]
    if status:
        rows = [item for item in rows if item["status"] == status]
    rows.sort(key=lambda item: item.get("startedAt") or "", reverse=True)
    start = (page - 1) * 20
    return {"items": rows[start : start + 20], "page": page, "total": len(rows)}


def _latest_prompt_version_id(agent_id: str) -> str | None:
    rows = [item for item in db.listing("version") if item["agentId"] == agent_id]
    if not rows:
        return None
    rows.sort(key=lambda item: item["version"])
    return rows[-1]["id"]


@router.post("/runs", status_code=201)
def create_run(body: dict):
    agent = db.get("agent", body.get("agentId", ""))
    if agent is None:
        return missing()
    key_error = missing_key_message(agent)
    if key_error:
        return error(422, "key_missing", key_error)
    if not (body.get("promptVersionId") or agent.get("activePromptVersionId") or _latest_prompt_version_id(agent["id"])):
        return error(422, "no_version", "No active prompt version")
    run = _new_run(agent, body)
    folder = db.projects_dir() / run["id"]
    folder.mkdir(parents=True, exist_ok=True)
    db.put("workspace", run["id"], {"folder": str(folder)})
    db.put("run", run["id"], run)
    from app.worker import start_run

    start_run(run["id"])
    return run


@router.get("/runs/{id}")
def get_run(id: str):
    return db.get("run", id) or missing()


@router.get("/runs/{id}/events")
def run_events(id: str, after: int = 0):
    if db.get("run", id) is None:
        return missing()

    def frames():
        from store import live

        yielded: set[str] = set()
        inbox = live.subscribe(id)
        last_beat = time.time()
        try:
            while True:
                pending = [event for event in db.events_for(id, after) if event["id"] not in yielded]
                for event in pending:
                    yielded.add(event["id"])
                    yield _frame(event)
                try:
                    live_event = inbox.get(timeout=0.05)
                except queue.Empty:
                    live_event = None
                if live_event and live_event["id"] not in yielded:
                    yielded.add(live_event["id"])
                    yield _frame(live_event)
                run = db.get("run", id)
                if run and run["status"] in ("completed", "failed", "cancelled") and live_event is None and inbox.empty():
                    for event in db.events_for(id, after):
                        if event["id"] not in yielded:
                            yielded.add(event["id"])
                            yield _frame(event)
                    break
                if time.time() - last_beat > 15:
                    last_beat = time.time()
                    # SSE comment keeps proxies from dropping the connection during long model calls.
                    yield ": ping\n\n"
        finally:
            live.unsubscribe(id, inbox)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/runs/{id}/stop")
def stop_run(id: str):
    run = db.get("run", id)
    if run is None:
        return missing()
    db.append_event(id, "STATE_CHANGED", {"status": "cancelled"})
    run["status"] = "cancelled"
    run["endedAt"] = db.now()
    db.put("run", id, run)
    bridge.wake(id)
    from runtime.openhands.runner import cancel_run

    cancel_run(id)
    if run.get("projectId"):
        from runtime import project_runs

        project_runs.drain(run["projectId"])
    return run


@router.post("/runs/{id}/client-tool-result")
def client_result(id: str, body: dict):
    run = db.get("run", id)
    if run is None:
        return missing()
    if run["status"] != "waiting_client":
        return error(409, "invalid", "The run is not waiting for a client tool")
    latest = next((item for item in reversed(db.events_for(id)) if item["type"] == "CLIENT_TOOL_REQUESTED"), None)
    if latest is None or latest["payload"].get("requestId") != body.get("requestId"):
        return error(409, "invalid", "requestId does not match")
    db.append_event(id, "TOOL_RESULT", {"name": "client", "output": body.get("output")})
    db.append_event(id, "STATE_CHANGED", {"status": "running"})
    run["status"] = "running"
    db.put("run", id, run)
    bridge.wake(id)
    return run


@router.post("/runs/{id}/answer")
def answer_run(id: str, body: dict):
    run = db.get("run", id)
    if run is None:
        return missing()
    if run["status"] != "waiting_user" or not body.get("text"):
        return error(409, "invalid", "The run is not waiting for an answer")
    db.put("answer", id, {"text": body["text"]})
    if run.get("projectId"):
        from runtime import needs

        needs.resolve_open(run["projectId"], body["text"], run_id=id, resume=False)
        _chat(run["projectId"], "user", body["text"], run.get("taskId"), run["id"])
    db.append_event(id, "STATE_CHANGED", {"status": "running"})
    run["status"] = "running"
    db.put("run", id, run)
    bridge.wake(id)
    return run


@router.get("/runs/{id}/diff")
def run_diff(id: str):
    if db.get("run", id) is None:
        return missing()
    return db.get("diff", id) or {"files": []}


@router.get("/runs/{id}/artifacts")
def run_artifacts(id: str, request: Request):
    run = db.get("run", id)
    if run is None:
        return missing()
    items = [item for item in db.listing("artifact") if item.get("runId") == id]
    if not any(item["kind"] == "zip" for item in items):
        zipped = _zip(id)
        if zipped:
            items.append(zipped)
    base = str(request.base_url)
    return [_public_artifact(item, base) for item in items]


@router.get("/artifact-files/{id}")
def artifact_file(id: str):
    item = db.get("artifact", id)
    if item is None or not item.get("path"):
        return missing()
    return FileResponse(item["path"])


@router.get("/projects")
def list_projects():
    return [_project_view(item) for item in db.listing("project")]


@router.post("/projects", status_code=201)
def create_project(body: dict):
    agent = db.get("agent", body.get("agentId", ""))
    if agent is None or not body.get("name"):
        return error(422, "invalid", "name and agentId are required")
    project_id = db.nid("prj")
    folder = db.projects_dir() / _slug(body["name"], project_id)
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=folder, capture_output=True)
    token_ref = _store_token(project_id, body.get("githubToken"), body.get("repoUrl"))
    from runtime import notes

    project = notes.defaults(
        {
            "id": project_id,
            "name": body["name"],
            "folderPath": str(folder),
            "repoUrl": body.get("repoUrl") or None,
            "tokenRef": token_ref,
            "members": [body["agentId"]],
            "localMode": bridge.local_mode(),
            "previewUrl": None,
            "createdAt": db.now(),
            "notesPath": body.get("notesPath"),
            "notesMaxBytes": body.get("notesMaxBytes"),
        }
    )
    db.put("project", project_id, project)
    return _project_view(project)


@router.get("/projects/{id}")
def get_project(id: str):
    project = db.get("project", id)
    return _project_view(project) if project else missing()


@router.patch("/projects/{id}")
def patch_project(id: str, body: dict):
    project = db.get("project", id)
    if project is None:
        return missing()
    if "notesPath" in body and body.get("notesPath"):
        project["notesPath"] = str(body["notesPath"]).replace("\\", "/").lstrip("/")
    if "notesMaxBytes" in body:
        try:
            project["notesMaxBytes"] = int(body["notesMaxBytes"])
        except (TypeError, ValueError):
            return error(422, "invalid", "notesMaxBytes must be an integer")
    if "repoUrl" in body:
        project["repoUrl"] = str(body["repoUrl"]).strip() or None
    # The token is write-only: it is stored by reference and never returned. A
    # non-empty value replaces the stored secret; the field is otherwise left
    # untouched so a settings save without a token keeps the existing one.
    if body.get("githubToken"):
        project["tokenRef"] = _store_token(id, body["githubToken"], project.get("repoUrl"))
    elif "repoUrl" in body and project.get("tokenRef") in (None, "env:GITHUB_TOKEN"):
        project["tokenRef"] = _store_token(id, None, project.get("repoUrl"))
    db.put("project", id, project)
    return _project_view(project)


@router.post("/projects/{id}/open-folder")
def open_project_folder(id: str):
    project = db.get("project", id)
    if project is None:
        return missing()
    if not bridge.local_mode():
        return error(409, "not_local", "Opening the folder is only available in local mode")
    folder = Path(project["folderPath"])
    if not folder.is_dir():
        return error(404, "missing", "Project folder does not exist on disk")
    opener = {"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open")
    try:
        # folder is the stored project path (not user input) and is passed as an
        # argv list, so there is no shell interpolation.
        subprocess.Popen([opener, str(folder)], start_new_session=True)
    except OSError as exc:
        return error(500, "open_failed", f"Could not open the folder: {exc}")
    return {"ok": True, "folderPath": str(folder)}


@router.post("/projects/{id}/push")
def push_project(id: str, body: dict | None = None):
    from runtime import github

    project = db.get("project", id)
    if project is None:
        return missing()
    if not project.get("repoUrl") or not project.get("tokenRef"):
        return error(422, "no_repo", "Set a GitHub repo URL and access token in project settings first.")
    folder = Path(project["folderPath"])
    if not folder.is_dir():
        return error(404, "missing", "Project folder does not exist on disk")
    message = (body or {}).get("message") or f"{project['name']} — pushed from Agent Studio"
    result = github.push_workspace(project, folder, str(message))
    if not result.get("ok"):
        return error(422, "push_failed", result.get("reason") or "Could not push to GitHub.")
    return {
        "ok": True,
        "branch": result.get("branch"),
        "prUrl": result.get("prUrl"),
        "repoUrl": result.get("repoUrl"),
    }


@router.post("/projects/{id}/members")
def add_project_member(id: str, body: dict):
    from runtime import members as memberlib

    project = db.get("project", id)
    if project is None:
        return missing()
    agent = db.get("agent", body.get("agentId") or "")
    if agent is None:
        return error(422, "invalid", "agentId is required")
    members = list(project.get("members") or [])
    if agent["id"] in members:
        return _project_view(project)
    overlap = memberlib.member_overlap(project, agent)
    if overlap:
        return error(409, "overlap", "Overlapping zones cannot be saved: " + ", ".join(overlap), {"overlapZones": overlap})
    members.append(agent["id"])
    project["members"] = members
    db.put("project", project["id"], project)
    return _project_view(project)


@router.delete("/projects/{id}", status_code=204)
def delete_project(id: str):
    from runtime import project_runs

    project = db.get("project", id)
    if project is None:
        return missing()
    project_runs.stop_all(id)
    bridge.stop_preview(id)
    for kind in ("preview", "project-spend"):
        db.delete(kind, id)
    run_ids = {item["id"] for item in db.listing("run") if item.get("projectId") == id}
    # One pass over events instead of re-listing the whole event table per run.
    for event in db.listing("event"):
        if event.get("runId") in run_ids:
            db.delete("event", event["id"])
    for run_id in run_ids:
        for kind in ("workspace", "run-track", "clarify", "answer", "diff", "event-seq"):
            db.delete(kind, run_id)
        db.delete("run", run_id)
    for task in db.listing("task"):
        if task.get("projectId") == id:
            for kind in ("handoff", "review-feedback"):
                for item in db.listing(kind):
                    if item.get("taskId") == task["id"]:
                        db.delete(kind, item["id"])
            db.delete("task", task["id"])
    for message in db.listing("message"):
        if message.get("projectId") == id:
            db.delete("message", message["id"])
    db.delete("project", id)


@router.get("/projects/{id}/messages")
def list_messages(id: str):
    if db.get("project", id) is None:
        return missing()
    rows = [item for item in db.listing("message") if item["projectId"] == id]
    for item in rows:
        plan_id = item.get("planId")
        if not plan_id or item.get("verdict"):
            continue
        plan = db.get("plan", plan_id)
        if plan and plan.get("status") == "approved":
            item["verdict"] = "approve"
    return sorted(rows, key=lambda item: item["createdAt"])


@router.post("/projects/{id}/messages", status_code=201)
def post_message(id: str, body: dict):
    from runtime import classify as labeling
    from runtime import lead as leadlib
    from runtime import project_runs

    project = db.get("project", id)
    if project is None:
        return missing()
    if not body.get("text"):
        return error(422, "invalid", "text is required")
    message_id = db.nid("msg")
    from runtime import needs as needslib

    waiting = [
        item
        for item in db.listing("run")
        if item.get("projectId") == id and item.get("status") == "waiting_user"
    ]
    if waiting and not bridge.is_preview_stop(body["text"]) and not bridge.is_control(body["text"]):
        latest = waiting[-1]
        user = _chat(id, "user", body["text"], latest.get("taskId"), latest["id"], message_id)
        needslib.resolve_open(id, body["text"])
        return user
    if bridge.is_preview_stop(body["text"]):
        user = _chat(id, "user", body["text"], None, None, message_id, "chat")
        had_preview = bool(db.get("preview", id))
        bridge.stop_preview(id)
        reply = "Preview stopped." if had_preview else "No preview is running."
        _chat(id, "agent", reply, None, None)
        return user
    if bridge.is_control(body["text"]):
        user = _chat(id, "user", body["text"], None, None, message_id)
        project_runs.stop_all(id)
        needslib.resolve_open(id, body["text"])
        _chat(id, "agent", "stopped", None, None)
        return user
    needslib.resolve_open(id, body["text"])
    task = {
        "id": db.nid("task"),
        "projectId": id,
        "parentTaskId": None,
        "text": body["text"],
        "assignedAgentId": "",
        "routedBy": "user",
        "status": "queued",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
    }
    bridge.route_task(project, task)
    work_text = task.get("text") or body["text"]
    if task.get("children"):
        cap = leadlib.spend_cap((db.get("settings", "runs") or {}).get("maxSpendPerDayUsd"), 0)
        if cap is not None and project_runs.spend_today(id) >= cap:
            return error(429, "budget", "The daily spend cap for this project was reached.")
        task["label"] = "task"
        db.put("task", task["id"], task)
        user = _chat(id, "user", body["text"], task["id"], None, message_id, "task")
        first_run = None
        for child in task["children"]:
            child_task = {
                "id": db.nid("task"),
                "projectId": id,
                "parentTaskId": task["id"],
                "text": child["text"],
                "assignedAgentId": child["assignedAgentId"],
                "routedBy": "rule",
                "status": "queued",
                "summary": None,
                "diffRef": None,
                "screenshotRefs": [],
                "label": "task",
            }
            db.put("task", child_task["id"], child_task)
            child_agent = db.get("agent", child["assignedAgentId"]) or {}
            _chat(id, "agent", f"{child_agent.get('name') or 'Agent'} will handle this part.", child_task["id"], None, None, "task", child_agent)
            run_message = _start_project_run(project, child_agent, child_task, child["text"], None, labeling.prior_context(id))
            if first_run is None:
                first_run = run_message
        if first_run:
            user["runId"] = first_run.get("runId")
            user["statusNote"] = "Split into member tasks"
            db.put("message", user["id"], user)
        return user
    agent = db.get("agent", task["assignedAgentId"]) or {}

    kind = bridge.classify(agent, work_text, id) if agent else "task"
    if leadlib.is_lead(agent) and kind == "out":
        kind = "task"
    if kind in ("chat", "out") and labeling.looks_like_task(agent, work_text, id):
        kind = "task"
    task["label"] = kind
    db.put("task", task["id"], task)
    if kind == "chat":
        user = _chat(id, "user", body["text"], task["id"], None, message_id, "chat")
        reply = bridge.chat_reply(agent, work_text, id)
        _chat(id, "agent", reply, task["id"], None, None, None, agent)
        task["status"] = "completed"
        task["summary"] = reply
        db.put("task", task["id"], task)
        return user
    if kind == "out":
        user = _chat(id, "user", body["text"], task["id"], None, message_id, "out")
        reply = bridge.refusal(agent, work_text)
        _chat(id, "agent", reply, task["id"], None, None, None, agent)
        task["status"] = "completed"
        task["summary"] = reply
        db.put("task", task["id"], task)
        return user
    cap = leadlib.spend_cap((db.get("settings", "runs") or {}).get("maxSpendPerDayUsd"), 0)
    if cap is not None and project_runs.spend_today(id) >= cap:
        return error(429, "budget", "The daily spend cap for this project was reached.")
    kind = "lead" if leadlib.is_lead(agent) else None
    return _start_project_run(project, agent, task, work_text, message_id, labeling.prior_context(id), kind=kind)


@router.get("/projects/{id}/tasks")
def list_task_board(id: str):
    from runtime import board as boardlib

    if db.get("project", id) is None:
        return missing()
    return boardlib.project_board(id)


@router.get("/projects/{id}/tasks/{taskId}")
def get_task_board(id: str, taskId: str):
    from runtime import board as boardlib

    if db.get("project", id) is None:
        return missing()
    detail = boardlib.detail(id, taskId)
    return detail if detail else missing()


@router.post("/projects/{id}/plans/{planId}/approve")
def approve_plan(id: str, planId: str, body: dict | None = None):
    from runtime import lead as leadlib

    if db.get("project", id) is None:
        return missing()
    try:
        return leadlib.approve_plan(id, planId, (body or {}).get("items"))
    except KeyError:
        return missing()


@router.post("/projects/{id}/plans/{planId}/edit")
def edit_plan(id: str, planId: str, body: dict):
    from runtime import lead as leadlib

    if db.get("project", id) is None:
        return missing()
    try:
        return leadlib.edit_plan(id, planId, body.get("items") or [])
    except KeyError:
        return missing()


def _start_project_run(project: dict, agent: dict, task: dict, text: str, message_id: str | None, prior: dict | None, kind: str | None = None):
    from runtime import project_runs

    key_error = missing_key_message(agent)
    if key_error:
        return error(422, "key_missing", key_error)
    run = _new_run(agent, {"task": text, "workspace": _workspace(project), "criteria": []})
    run["taskId"] = task["id"]
    run["projectId"] = project["id"]
    if kind:
        run["kind"] = kind
    if prior:
        run["priorContext"] = prior
    db.put("workspace", run["id"], {"folder": project["folderPath"]})
    queued = project_runs.working(project["id"]) is not None
    run["status"] = "queued" if queued else "running"
    db.put("run", run["id"], run)
    message = None
    if message_id:
        message = {
            "id": message_id,
            "projectId": project["id"],
            "role": "user",
            "text": text,
            "taskId": task["id"],
            "runId": run["id"],
            "label": "task",
            "createdAt": db.now(),
        }
        if queued:
            message["queueStatus"] = "waiting"
            message["statusNote"] = "queued, will start after the current task"
        db.put("message", message["id"], message)
    task["status"] = "queued" if queued else "running"
    db.put("task", task["id"], task)
    if not queued:
        from app.worker import launch

        launch(run)
    return message or {"runId": run["id"], "taskId": task["id"]}


@router.post("/projects/{id}/close")
def close_project(id: str):
    project = db.get("project", id)
    if project is None:
        return missing()
    bridge.stop_preview(id)
    project = db.get("project", id)
    return _project_view(project)


@router.post("/projects/{id}/preview")
def start_preview(id: str):
    from runtime import tools

    project = db.get("project", id)
    if project is None:
        return missing()
    folder = Path(project["folderPath"])
    if not folder.is_dir():
        return error(404, "missing", "Project folder does not exist on disk")
    # _preview stops any existing server for this project first, so this doubles as a
    # restart. It serves the project folder (vite dev when there is a package.json,
    # otherwise a static server) and records the preview URL on the project.
    result = tools._preview({"id": id, "projectId": id, "folder": str(folder)}, folder)
    if not result.get("previewUrl"):
        return error(500, "preview_failed", "Could not start the preview server")
    return _project_view(db.get("project", id))


def _frame(event: dict) -> str:
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


def _chat(project_id: str, role: str, text: str, task_id: str | None, run_id: str | None, message_id: str | None = None, label: str | None = None, agent: dict | None = None) -> dict:
    from runtime import members as memberlib

    message = {
        "id": message_id or db.nid("msg"),
        "projectId": project_id,
        "role": role,
        "text": text,
        "createdAt": db.now(),
    }
    if label:
        message["label"] = label
    if task_id:
        message["taskId"] = task_id
    if run_id:
        message["runId"] = run_id
    if agent and role == "agent":
        message.update(memberlib.stamp(agent))
    db.put("message", message["id"], message)
    return message


@router.post("/agents/{id}/teach", status_code=201)
def teach_agent(id: str, body: dict):
    if db.get("agent", id) is None:
        return missing()
    try:
        result = bridge.teach_agent(id, body)
    except ValueError as exc:
        return error(422, "invalid", str(exc))
    return result or missing()


@router.post("/agents/{id}/teach/draft")
def teach_draft(id: str, body: dict):
    if db.get("agent", id) is None:
        return missing()
    if not body.get("repoUrl"):
        return error(422, "invalid", "repoUrl is required")
    try:
        return {"rules": bridge.draft_rules(body["repoUrl"])}
    except RuntimeError as exc:
        return error(422, "invalid", str(exc))


def _agent(body: dict) -> dict:
    timestamp = db.now()
    stacks = body.get("stackIds") or []
    skills = body.get("skillIds") or []
    model = models_catalog.normalize_spec(body.get("model"))
    if not model:
        from runtime import fit

        model = models_catalog.normalize_spec(fit.default_model(body.get("roleKey")) or default_model_spec())
    return {
        "id": db.nid("agt"),
        "name": body.get("name"),
        "roleKey": body.get("roleKey"),
        "description": body.get("description") or "",
        "model": model,
        "backupModel": models_catalog.normalize_spec(body.get("backupModel")),
        "activePromptVersionId": None,
        "toolIds": body.get("toolIds") or [],
        "skillIds": skills,
        "stackIds": stacks,
        "zones": body.get("zones") or [],
        "scope": body.get("scope") or {"does": [], "neverDoes": [], "zones": body.get("zones") or []},
        "evals": body.get("evals") or [],
        "reportsTo": body.get("reportsTo"),
        "workerEngine": "openhands",
        "capabilities": {
            "stacks": (body.get("capabilities") or {}).get("stacks") or stacks,
            "skills": (body.get("capabilities") or {}).get("skills") or skills,
            "tags": (body.get("capabilities") or {}).get("tags") or [],
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def _save_version(agent: dict, sections: dict) -> dict:
    existing = [item for item in db.listing("version") if item["agentId"] == agent["id"]]
    from runtime import roles as rolelib

    compiled = bridge.compile_prompt(
        sections,
        agent["toolIds"],
        agent["skillIds"],
        agent["stackIds"],
        (agent.get("model") or {}).get("name") or "gpt-4o",
        agent.get("scope"),
        worker=not rolelib.is_supervisor(agent),
    )
    version = {
        "id": db.nid("pv"),
        "agentId": agent["id"],
        "version": len(existing) + 1,
        "sections": sections,
        "compiled": compiled["compiled"],
        "tokenCount": compiled["tokenCount"],
        "evalResults": [{"evalId": item["id"], "status": "not_run", "evidence": None} for item in agent.get("evals") or []],
        "createdAt": db.now(),
    }
    db.put("version", version["id"], version)
    return version


def _version(agent_id: str, number: int):
    return next((item for item in db.listing("version") if item["agentId"] == agent_id and item["version"] == number), None)


def _check_skill_size(body: str) -> None:
    from runtime.compile import token_count

    if token_count(body) > 8000:
        raise ValueError("put reference material in a data source; a skill is your rules (Tools > Data)")


def _skill(body: dict) -> dict:
    _check_skill_size(body.get("body") or "")
    timestamp = db.now()
    return {
        "id": body.get("id") or db.nid("skill"),
        "name": body.get("name") or "skill",
        "description": body.get("description") or "",
        "body": body.get("body") or "",
        "files": body.get("files") or [],
        "version": 1,
        "versions": [{"version": 1, "createdAt": timestamp}],
        "origin": body.get("origin") or "user",
        "createdAt": timestamp,
    }


def _import_skill(library: dict, skill_id: str) -> None:
    if db.get("skill", skill_id):
        return
    skill = next((item for item in library["skills"] if item["id"] == skill_id), None)
    if skill:
        db.put("skill", skill_id, skill)


def _import_stack(library: dict, stack_id: str) -> None:
    if db.get("stack", stack_id):
        return
    stack = next((item for item in library["stacks"] if item["id"] == stack_id), None)
    if not stack:
        return
    db.put("stack", stack_id, stack)
    for source_id in stack.get("dataSourceIds") or []:
        if db.get("datasource", source_id):
            continue
        source = next((item for item in library.get("dataSources") or [] if item["id"] == source_id), None)
        if source:
            db.put("datasource", source_id, source)


def _new_run(agent: dict, body: dict) -> dict:
    model = models_catalog.normalize_spec(body.get("model") or agent.get("model"))
    prompt_version_id = body.get("promptVersionId") or agent.get("activePromptVersionId") or _latest_prompt_version_id(agent["id"]) or ""
    return {
        "id": db.nid("run"),
        "agentId": agent["id"],
        "promptVersionId": prompt_version_id,
        "model": model,
        "workspace": body.get("workspace") or {"kind": "scaffold", "template": "local"},
        "task": body.get("task") or "",
        "criteria": body.get("criteria") or [],
        "attachmentIds": body.get("attachmentIds") or [],
        "status": "queued",
        "iterations": 0,
        "tokensIn": 0,
        "tokensOut": 0,
        "costUsd": 0,
        "startedAt": db.now(),
    }


def _workspace(project: dict) -> dict:
    if project.get("repoUrl"):
        return {"kind": "repo", "url": project["repoUrl"]}
    return {"kind": "scaffold", "template": "local"}


def _stats(name: str, agents: list[dict], runs: list[dict]) -> list[dict]:
    from runtime import fit

    stats = []
    roles = {agent["roleKey"] for agent in agents}
    for role in roles:
        overlay = fit.overlay(name, role)
        if overlay:
            stats.append(
                {
                    "roleKey": role,
                    "runs": overlay["runs"],
                    "passed": overlay["passed"],
                    "avgCostUsd": overlay["avgCostUsd"],
                    "avgRework": overlay["avgRework"],
                    "firstTryRate": overlay["firstTryRate"],
                    "suggested": overlay["suggested"],
                    "reason": overlay["reason"],
                }
            )
            continue
        ids = {agent["id"] for agent in agents if agent["roleKey"] == role}
        matched = [
            run
            for run in runs
            if models_catalog.model_id((run.get("model") or {}).get("name") or "") == models_catalog.model_id(name)
            and run.get("agentId") in ids
        ]
        if not matched:
            continue
        passed = [run for run in matched if run["status"] == "completed" and run.get("summary")]
        average = sum(run["costUsd"] for run in passed) / (len(passed) or 1)
        stats.append({"roleKey": role, "runs": len(matched), "passed": len(passed), "avgCostUsd": average, "reason": "not enough data yet"})
    return stats


def _public_artifact(item: dict, base: str) -> dict:
    public = {"id": item["id"], "name": item["name"], "kind": item["kind"]}
    if item.get("viewport"):
        public["viewport"] = item["viewport"]
    if item["kind"] == "log":
        public["url"] = "data:text/plain," + quote(item.get("text") or "")
    elif item.get("path"):
        public["url"] = base + "artifact-files/" + item["id"]
    elif item.get("url"):
        public["url"] = item["url"]
    return public


def _zip(run_id: str):
    workspace = db.get("workspace", run_id)
    if not workspace:
        return None
    folder = Path(workspace["folder"])
    if not folder.exists():
        return None
    target = folder / ".artifacts" / "project.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for path in folder.rglob("*"):
            if ".git" in path.parts or "node_modules" in path.parts or ".artifacts" in path.parts or not path.is_file():
                continue
            archive.write(path, path.relative_to(folder))
    artifact_id = db.nid("art")
    record = {"id": artifact_id, "runId": run_id, "name": "project.zip", "kind": "zip", "path": str(target)}
    db.put("artifact", artifact_id, record)
    return record


def _preview_alive(preview: dict) -> bool:
    """A preview must actually serve HTTP before it is offered. A bare TCP connect
    succeeds the moment the dev server binds the port, while it is still compiling
    the first request — the iframe would then load too early and show blank until a
    refresh. Require a real HTTP response so the URL appears only when it works."""
    import httpx

    url = preview.get("url") or ""
    if not url:
        return False
    try:
        response = httpx.get(url, timeout=1.0, follow_redirects=True)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def _project_view(project: dict) -> dict:
    from runtime import notes, project_runs

    project = notes.defaults({**project, "localMode": bridge.local_mode()})
    preview = db.get("preview", project["id"])
    if preview and _preview_alive(preview):
        project["previewUrl"] = preview["url"]
    active = project_runs.working(project["id"])
    project["activeRunId"] = active["id"] if active else None
    from runtime import members as memberlib

    project["memberDetails"] = memberlib.member_details(project)
    from runtime.supervisor.steps import steps_for_project

    project["supervisorSteps"] = steps_for_project(project["id"])
    return project


def _slug(name: str, project_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    return f"{slug}-{project_id}"


def _store_token(project_id: str, token: str | None, repo_url: str | None) -> str | None:
    if token:
        folder = db.projects_dir() / ".secrets"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / project_id
        path.write_text(token)
        path.chmod(0o600)
        return f"file:{project_id}"
    if repo_url and os.environ.get("GITHUB_TOKEN"):
        return "env:GITHUB_TOKEN"
    return None
