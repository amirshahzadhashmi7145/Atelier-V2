import hashlib
import json
import subprocess
from pathlib import Path

from runtime import route_task, sandbox
from store import db

CONTROL = ["load_skill", "complete", "raise_clarification", "escalate"]
SUPERVISOR = ["create_task", "record_review"]


def allowed(agent: dict) -> set[str]:
    names = set(agent.get("toolIds") or []) | set(CONTROL)
    tags = (agent.get("capabilities") or {}).get("tags") or []
    if "supervisor" in tags:
        names |= set(SUPERVISOR)
    return names


def openai_tools(agent: dict) -> list[dict]:
    catalog = {item["name"]: item for item in db.listing("tool")}
    result = []
    for name in allowed(agent):
        tool = catalog.get(name)
        if not tool:
            continue
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["schema"],
                },
            }
        )
    return result


def dispatch(run: dict, name: str, arguments: dict, should_stop) -> dict:
    agent = db.get("agent", run["agentId"]) or {}
    if name not in allowed(agent):
        return {"refused": True, "reason": f"{name} is outside the allow-list"}
    folder = Path(run["folder"]) if run.get("folder") else None
    if name == "files":
        return _files(run, folder, arguments)
    if name == "shell":
        return _shell(folder, arguments.get("command", ""), should_stop)
    if name == "package_install":
        return _install(run, folder, arguments.get("name", ""), should_stop)
    if name == "build_test":
        return _build(run, folder, should_stop)
    if name == "headless_browser":
        return _browser(run, arguments.get("url") or "")
    if name == "preview_deploy":
        return _preview(run, folder)
    if name == "search_data":
        return _search(agent, arguments.get("query", ""))
    if name == "load_skill":
        return _skill(run, folder, arguments.get("name", ""))
    if name == "complete":
        return {"done": True, "summary": arguments.get("summary") or {}}
    if name == "raise_clarification":
        return {"clarify": arguments.get("question") or "Need a decision"}
    if name == "escalate":
        return {"done": True, "summary": {"description": arguments.get("reason") or "Escalated", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
    if name == "create_task":
        return _create_task(run, arguments)
    if name == "record_review":
        return _review(run, arguments)
    return {"refused": True, "reason": f"unknown tool {name}"}


def _files(run: dict, folder: Path | None, arguments: dict) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    path = arguments.get("path") or ""
    try:
        target = sandbox.guard_path(folder, path)
    except PermissionError:
        return {"refused": True, "reason": f"path outside the project: {path}"}
    op = arguments.get("op") or "read"
    before = target.read_text() if target.exists() and target.is_file() else ""
    if op == "read":
        return {"output": before}
    if op == "write":
        target.parent.mkdir(parents=True, exist_ok=True)
        content = arguments.get("content") or ""
        target.write_text(content)
        _diff(run["id"], path, before, content)
        return {"output": "wrote", "changed": before != content}
    if op == "edit":
        old = arguments.get("old") or ""
        new = arguments.get("new") or ""
        content = before.replace(old, new, 1) if old and old in before else before
        target.write_text(content)
        _diff(run["id"], path, before, content)
        return {"output": "edited", "changed": before != content}
    return {"refused": True, "reason": "unknown file op"}


def _diff(run_id: str, path: str, before: str, after: str) -> None:
    current = db.get("diff", run_id) or {"files": []}
    found = next((item for item in current["files"] if item["path"] == path), None)
    if found:
        found["after"] = after
    else:
        current["files"].append({"path": path, "before": before, "after": after})
    db.put("diff", run_id, current)


def _shell(folder: Path | None, command: str, should_stop) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    try:
        code, output = sandbox.run_command(folder, command, should_stop)
    except PermissionError:
        return {"refused": True, "reason": "command leaves the project folder"}
    return {"output": output, "exitCode": code}


def _allow_list(agent: dict) -> set[str]:
    stacks = {item["id"]: item for item in db.listing("stack")}
    names: set[str] = set()
    for stack_id in agent.get("stackIds") or []:
        stack = stacks.get(stack_id)
        if stack and stack.get("enabledByDefault", True):
            names.update(stack.get("packageAllowList") or [])
    return names


def _install(run: dict, folder: Path | None, name: str, should_stop) -> dict:
    agent = db.get("agent", run["agentId"]) or {}
    if name not in _allow_list(agent):
        return {"refused": True, "reason": f"{name} is not on an enabled stack allow-list"}
    return _shell(folder, f"npm install {name}", should_stop)


def _build(run: dict, folder: Path | None, should_stop) -> dict:
    if folder is None or not (folder / "package.json").exists():
        db.put("artifact", db.nid("art"), {"id": "pending", "runId": run["id"], "name": "build.log", "kind": "log", "text": "no package.json"})
        return {"output": "no package.json"}
    package = json.loads((folder / "package.json").read_text())
    scripts = package.get("scripts") or {}
    log = ""
    for script in ("build", "test"):
        if script in scripts:
            code, output = sandbox.run_command(folder, f"npm run {script}", should_stop)
            log += output
            if code:
                break
    artifact_id = db.nid("art")
    db.put("artifact", artifact_id, {"id": artifact_id, "runId": run["id"], "name": f"{script}.log", "kind": "log", "text": log})
    return {"output": log or "no build or test script"}


def _browser(run: dict, url: str) -> dict:
    folder = Path(run["folder"]) if run.get("folder") else Path(".")
    shots = folder / ".artifacts"
    shots.mkdir(parents=True, exist_ok=True)
    viewports = [("mobile", 390, 844), ("tablet", 768, 1024), ("desktop", 1280, 800)]
    script = db.ROOT / "web" / "node_modules" / "playwright"
    errors = ""
    if url and script.exists():
        node = f"""
        const {{ chromium }} = require({json.dumps(str(script))});
        (async () => {{
          const browser = await chromium.launch();
          const page = await browser.newPage();
          const errors = [];
          page.on('pageerror', (error) => errors.push(String(error)));
          for (const [name, width, height] of {json.dumps(viewports)}) {{
            await page.setViewportSize({{ width, height }});
            await page.goto({json.dumps(url)});
            await page.screenshot({{ path: {json.dumps(str(shots))} + '/' + name + '.png' }});
          }}
          console.log(JSON.stringify(errors));
          await browser.close();
        }})();
        """
        result = subprocess.run(["node", "-e", node], capture_output=True, text=True)
        errors = result.stdout
    artifacts = []
    for name, _width, _height in viewports:
        path = shots / f"{name}.png"
        if not path.exists():
            path.write_bytes(b"")
        artifact_id = db.nid("art")
        record = {"id": artifact_id, "runId": run["id"], "name": f"{name}.png", "kind": "screenshot", "viewport": name, "path": str(path)}
        db.put("artifact", artifact_id, record)
        artifacts.append(artifact_id)
    return {"output": errors or "captured", "screenshots": artifacts}


def _preview(run: dict, folder: Path | None) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    if (folder / "package.json").exists():
        command = f"npm run dev -- --port {port} --host 127.0.0.1"
    else:
        command = f"python3 -m http.server {port}"
    process = subprocess.Popen(command, cwd=folder, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    db.put("preview", run.get("projectId") or run["id"], {"pid": process.pid, "url": url})
    if run.get("projectId"):
        project = db.get("project", run["projectId"])
        if project:
            project["previewUrl"] = url
            db.put("project", project["id"], project)
    return {"output": url, "previewUrl": url}


def _search(agent: dict, query: str) -> dict:
    hits = []
    for source_id in agent.get("dataSourceIds") or []:
        source = db.get("datasource", source_id)
        if source and query.lower() in (source.get("name", "") + source.get("ref", "")).lower():
            hits.append(source["name"])
    return {"output": hits}


def _skill(run: dict, folder: Path | None, name: str) -> dict:
    skills = db.listing("skill")
    skill = next((item for item in skills if item["name"] == name or item["id"] == name), None)
    if skill is None:
        return {"refused": True, "reason": f"unknown skill {name}"}
    if folder is not None:
        target = folder / ".skills" / skill["name"]
        target.mkdir(parents=True, exist_ok=True)
        for skill_file in skill.get("files") or []:
            path = sandbox.guard_path(target, skill_file.get("path") or "skill.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skill_file.get("content") or "")
        (target / "SKILL.md").write_text(skill.get("body") or "")
    db.append_event(run["id"], "SKILL_LOADED", {"name": skill["name"]})
    return {"output": skill.get("body") or "", "skill": skill["name"]}


def _create_task(run: dict, arguments: dict) -> dict:
    project = db.get("project", run.get("projectId"))
    if project is None:
        return {"refused": True, "reason": "no project"}
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": arguments.get("parentTaskId") or run.get("taskId"),
        "text": arguments.get("text") or "",
        "assignedAgentId": arguments.get("assignToAgentId") or "",
        "routedBy": "agent",
        "status": "queued",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
    }
    if not task["assignedAgentId"]:
        route_task.route_task(project, task)
        task["routedBy"] = "agent"
    db.put("task", task["id"], task)
    return {"output": task["id"], "taskId": task["id"]}


def _review(run: dict, arguments: dict) -> dict:
    task = db.get("task", arguments.get("taskId") or "")
    if task is None:
        return {"refused": True, "reason": "unknown task"}
    text = f"{arguments.get('verdict')}: {arguments.get('notes') or ''}".strip()
    message = {
        "id": db.nid("msg"),
        "projectId": task["projectId"],
        "role": "agent",
        "text": text,
        "taskId": task["id"],
        "createdAt": db.now(),
    }
    db.put("message", message["id"], message)
    return {"output": text}


def call_hash(name: str, arguments: dict) -> str:
    raw = json.dumps({"name": name, "arguments": arguments}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def stop_preview(project_id: str) -> None:
    record = db.get("preview", project_id)
    if not record:
        return
    try:
        os_kill(record["pid"])
    except ProcessLookupError:
        pass
    db.delete("preview", project_id)
    project = db.get("project", project_id)
    if project:
        project["previewUrl"] = None
        db.put("project", project["id"], project)


def os_kill(pid: int) -> None:
    import os
    import signal

    os.kill(pid, signal.SIGTERM)
