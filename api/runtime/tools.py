import hashlib
import json
import subprocess
from fnmatch import fnmatch
from pathlib import Path

from runtime import route_task, sandbox
from runtime.tool_results import READ_CAP, format_tool_result
from store import db

__all__ = ["allowed", "call_hash", "dispatch", "format_tool_result", "openai_tools", "stop_preview"]

CONTROL = ["load_skill", "complete", "raise_clarification", "escalate"]
SUPERVISOR = ["create_task", "record_review"]


def allowed(agent: dict) -> set[str]:
    names = set(agent.get("toolIds") or []) | set(CONTROL)
    from runtime import lead as leadlib

    if leadlib.is_lead(agent):
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
        return _files(run, folder, arguments, (agent.get("scope") or {}).get("zones") or [])
    if name == "shell":
        blocked = _blocked_command(agent, arguments.get("command", ""))
        if blocked:
            return {"refused": True, "reason": blocked}
        from runtime import lead as leadlib

        command = arguments.get("command", "")
        if (run.get("kind") in ("lead", "review") or leadlib.is_lead(agent)) and not _build_or_test_command(command):
            return {"refused": True, "reason": "a supervisor may only run build and test commands"}
        return _shell(folder, command, should_stop)
    if name == "package_install":
        from runtime import lead as leadlib

        if run.get("kind") in ("lead", "review") or leadlib.is_lead(agent):
            return {"refused": True, "reason": "a supervisor cannot install packages"}
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
        from runtime import lead as leadlib

        if run.get("kind") in ("lead", "review") or leadlib.is_lead(agent):
            return {"done": True, "summary": arguments.get("summary") or {}}
        track = db.get("run-track", run["id"]) or {}
        folder = Path(run["folder"]) if run.get("folder") else None
        has_pkg = folder is not None and (folder / "package.json").exists()
        if has_pkg and track.get("lastBuildOk") is not True:
            reason = track.get("lastBuildReason") or "Run build_test and fix failures before complete."
            return {"refused": True, "reason": reason}
        return {"done": True, "summary": arguments.get("summary") or {}}
    if name == "raise_clarification":
        raw = arguments.get("questions")
        if not isinstance(raw, list):
            raw = [arguments.get("question") or "Need a decision"]
        questions = [str(item).strip() for item in raw if str(item).strip()][:3] or ["Need a decision"]
        if _asks_to_change_scope("\n".join(questions)):
            return {"scopeEnd": True, "reason": "You cannot enable stacks or change your own scope. Only the user can."}
        return {"clarify": "\n".join(questions), "questions": questions}
    if name == "escalate":
        return {"done": True, "summary": {"description": arguments.get("reason") or "Escalated", "filesChanged": [], "dependencies": [], "criteria": [], "assumptions": [], "followUps": []}}
    if name == "create_task":
        return _create_task(run, arguments)
    if name == "record_review":
        return _review(run, arguments)
    return {"refused": True, "reason": f"unknown tool {name}"}


def _files(run: dict, folder: Path | None, arguments: dict, zones: list[str] | None = None) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    path = arguments.get("path") or ""
    op = arguments.get("op") or "read"
    write_ops = {"write", "edit", "append"}
    from runtime import lead as leadlib

    agent = db.get("agent", run.get("agentId") or "") or {}
    if op in write_ops and (run.get("kind") in ("lead", "review") or leadlib.is_lead(agent)):
        return {"refused": True, "reason": "a supervisor cannot write files"}
    if op in write_ops:
        from runtime import notes

        project = db.get("project", run.get("projectId") or "") or {}
        if notes.is_protected(path, project):
            return {"refused": True, "reason": f"workers cannot edit the notes file: {path}"}
    if op in write_ops and zones and not _in_zones(path, zones):
        return {"refused": True, "reason": f"path outside your zones: {path}"}
    from runtime import members as memberlib

    if op in write_ops and memberlib.is_shared_path(path) and memberlib.other_member_busy(run):
        return {"refused": True, "reason": f"writes to {path} wait until the other project member is idle"}
    try:
        target = sandbox.guard_path(folder, path)
    except PermissionError:
        return {"refused": True, "reason": f"path outside the project: {path}"}
    before = target.read_text() if target.exists() and target.is_file() else ""
    if op == "list":
        if not target.exists():
            return {"output": "(empty directory listing)"}
        if target.is_file():
            return {"output": path}
        lines = []
        for child in sorted(target.rglob("*")):
            if ".git" in child.parts or "node_modules" in child.parts:
                continue
            if child.is_file():
                lines.append(str(child.relative_to(folder)))
        return {"output": "\n".join(lines[:200]) or "(empty directory listing)"}
    if op == "read":
        if not before.strip():
            return {"output": "(file is empty)"}
        if len(before) > READ_CAP:
            return {"output": before[:READ_CAP] + "\n(note: file truncated at 20 kB)"}
        return {"output": before}
    if op == "list":
        if not target.exists():
            return {"output": ""}
        if target.is_file():
            return {"output": path}
        lines = []
        for child in sorted(target.rglob("*")):
            if ".git" in child.parts or "node_modules" in child.parts:
                continue
            if child.is_file():
                lines.append(str(child.relative_to(folder)))
        return {"output": "\n".join(lines[:200])}
    if op == "write":
        target.parent.mkdir(parents=True, exist_ok=True)
        content = arguments.get("content") or ""
        existed = target.exists() and target.is_file()
        target.write_text(content)
        _diff(run["id"], folder, path, before, content)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return {
            "output": f"wrote {len(content)} bytes hash {digest}",
            "changed": before != content,
            "fullWrite": existed,
            "path": path,
            "size": len(content),
            "hash": digest,
        }
    if op == "edit":
        old = arguments.get("old_text") or arguments.get("old") or ""
        new_given = next((key for key in ("new_text", "new") if key in arguments), None)
        new = (arguments.get(new_given) or "") if new_given else ""
        if not target.exists():
            return {"refused": True, "reason": "file missing; use write for new files"}
        if not old:
            return {"refused": True, "reason": "edit needs old_text; use write to replace the whole file"}
        if new_given is None:
            # The model sent `content` (or nothing) instead of new_text; silently deleting old_text would gut the file.
            return {"refused": True, "reason": "edit needs new_text (the replacement for old_text); use write to replace the whole file"}
        if old not in before:
            return {"output": "old_text not found; no change", "changed": False}
        content = before.replace(old, new, 1)
        target.write_text(content)
        _diff(run["id"], folder, path, before, content)
        return {"output": "edited", "changed": before != content}
    if op == "append":
        target.parent.mkdir(parents=True, exist_ok=True)
        chunk = arguments.get("content") or ""
        content = before + chunk
        target.write_text(content)
        _diff(run["id"], folder, path, before, content)
        return {"output": "appended", "changed": bool(chunk)}
    return {"refused": True, "reason": "unknown file op"}


def _diff(run_id: str, folder: Path, path: str, before: str, after: str) -> None:
    current = db.get("diff", run_id) or {"files": []}
    found = next((item for item in current["files"] if item["path"] == path), None)
    if found:
        found["after"] = after
    else:
        current["files"].append({"path": path, "before": before, "after": after})
    db.put("diff", run_id, current)
    target = folder / path
    if target.exists() and folder.joinpath(".git").exists():
        subprocess.run(["git", "add", "-N", path], cwd=folder, capture_output=True)


def _shell(folder: Path | None, command: str, should_stop, timeout: float = 120) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    if _long_running(command):
        return {"refused": True, "reason": "This command does not exit. Use the preview tool."}
    try:
        code, output = sandbox.run_command(folder, command, should_stop, timeout=min(600, timeout))
    except PermissionError:
        return {"refused": True, "reason": "command leaves the project folder"}
    if output == "timed out":
        return {"output": "timed out", "exitCode": code, "error": True}
    return {"output": output, "exitCode": code}


def _in_zones(path: str, zones: list[str]) -> bool:
    pure = path.replace("\\", "/").lstrip("/")
    while pure.startswith("./"):
        pure = pure[2:]
    for zone in zones:
        pattern = zone.replace("\\", "/").lstrip("/")
        if fnmatch(pure, pattern):
            return True
    return False


def _blocked_command(agent: dict, command: str) -> str | None:
    never = [item.lower() for item in ((agent.get("scope") or {}).get("neverDoes") or [])]
    low = command.lower()
    if any("server" in item for item in never) and any(token in low for token in ("node server.js", "uvicorn", "docker compose up")):
        return "That is outside your role. You do not create servers."
    if any("database" in item for item in never) and "migration" in low:
        return "That is outside your role. You do not create databases."
    return None


def _asks_to_change_scope(text: str) -> bool:
    low = text.lower()
    return ("enable" in low and "stack" in low) or "change scope" in low or "change your scope" in low or "change my scope" in low


def _build_or_test_command(command: str) -> bool:
    low = (command or "").lower()
    tokens = ("npm run build", "npm run test", "npm test", "pnpm test", "pnpm run build", "pnpm run test", "npx vitest", "node --test", "pytest")
    return any(token in low for token in tokens) and not _long_running(low)


def _long_running(command: str) -> bool:
    low = command.lower()
    return any(token in low for token in ("npm run dev", "npm start", "next dev", "vite", "webpack serve", "nodemon", "--watch", "http.server"))


def _allow_list(agent: dict) -> set[str]:
    stacks = {item["id"]: item for item in db.listing("stack")}
    names: set[str] = set()
    for stack_id in agent.get("stackIds") or []:
        stack = stacks.get(stack_id)
        if stack and stack.get("enabledByDefault", True):
            names.update(stack.get("packageAllowList") or [])
    return names


def _package_allowed(agent: dict, name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in _allow_list(agent))


def _install(run: dict, folder: Path | None, name: str, should_stop) -> dict:
    agent = db.get("agent", run["agentId"]) or {}
    if not _package_allowed(agent, name):
        return {"refused": True, "reason": f"{name} is not on an enabled stack allow-list"}
    return _shell(folder, f"npm install {name}", should_stop)


def _build(run: dict, folder: Path | None, should_stop) -> dict:
    log = ""
    ok = False
    if folder is not None and (folder / "package.json").exists():
        try:
            package = json.loads((folder / "package.json").read_text())
        except json.JSONDecodeError:
            package = None
        if not isinstance(package, dict):
            log = "package.json is not valid JSON; rewrite it with files.write"
            package = {}
        scripts = package.get("scripts") or {}
        ok = "build" in scripts and "test" in scripts and not log
        for script in ("build", "test"):
            if script not in scripts:
                ok = False
                log += f'package.json has no "{script}" script; add one under "scripts"\n'
                continue
            code, output = sandbox.run_command(folder, f"npm run {script}", should_stop)
            log += output
            if code:
                ok = False
                break
    else:
        log = "no package.json"
    artifact_id = db.nid("art")
    db.put("artifact", artifact_id, {"id": artifact_id, "runId": run["id"], "name": "build.log", "kind": "log", "text": log, "ok": ok})
    tail = log[-8000:] if len(log) > 8000 else log
    if len(log) > 8000:
        tail = "… truncated …\n" + tail
    return {"output": tail or "no build or test script", "buildOk": ok, "buildLog": tail}


def _browser(run: dict, url: str) -> dict:
    folder = Path(run["folder"]) if run.get("folder") else Path(".")
    shots = folder / ".artifacts"
    shots.mkdir(parents=True, exist_ok=True)
    viewports = [("mobile", 390, 844), ("tablet", 768, 1024), ("desktop", 1280, 800)]
    script = _playwright_package()
    errors = ""
    launched = False
    target = url or ""
    if target and not target.startswith(("http://", "https://", "file://")):
        target = (folder / target).resolve().as_uri()
    if target and script is not None and script.exists():
        node = f"""
        const {{ chromium }} = require({json.dumps(str(script))});
        (async () => {{
          const browser = await chromium.launch();
          const page = await browser.newPage();
          const errors = [];
          page.on('pageerror', (error) => errors.push(String(error)));
          for (const [name, width, height] of {json.dumps(viewports)}) {{
            await page.setViewportSize({{ width, height }});
            await page.goto({json.dumps(target)});
            await page.screenshot({{ path: {json.dumps(str(shots))} + '/' + name + '.png' }});
          }}
          console.log(JSON.stringify(errors));
          await browser.close();
        }})();
        """
        result = subprocess.run(["node", "-e", node], capture_output=True, text=True)
        errors = result.stdout
        launched = result.returncode == 0
    console: list = []
    if errors.strip().startswith("["):
        try:
            console = json.loads(errors)
        except json.JSONDecodeError:
            console = [errors]
    artifacts = []
    unavailable = False
    for name, width, height in viewports:
        path = shots / f"{name}.png"
        ok = launched and _png_matches(path, width, height)
        if not ok:
            unavailable = True
            continue
        artifact_id = db.nid("art")
        record = {
            "id": artifact_id,
            "runId": run["id"],
            "name": f"{name}.png",
            "kind": "screenshot",
            "viewport": name,
            "path": str(path),
            "ok": True,
            "consoleErrors": console,
        }
        db.put("artifact", artifact_id, record)
        artifacts.append(artifact_id)
    if unavailable or not artifacts:
        return {"output": "screenshot unavailable", "screenshots": artifacts, "screenshotFailed": True}
    return {"output": errors or "captured", "screenshots": artifacts}


def _playwright_package() -> Path | None:
    direct = db.ROOT / "web" / "node_modules" / "playwright"
    if (direct / "package.json").exists():
        return direct
    nested = db.ROOT / "web" / "node_modules" / ".pnpm"
    if not nested.is_dir():
        return None
    matches = sorted(nested.glob("playwright@*/node_modules/playwright/package.json"))
    return matches[-1].parent if matches else None


def _png_matches(path: Path, width: int, height: int) -> bool:
    if not path.exists() or path.stat().st_size < 24:
        return False
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return False
    got_w = int.from_bytes(data[16:20], "big")
    got_h = int.from_bytes(data[20:24], "big")
    return got_w == width and got_h == height


def _preview(run: dict, folder: Path | None) -> dict:
    if folder is None:
        return {"output": "no workspace"}
    import socket

    folder.mkdir(parents=True, exist_ok=True)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    if (folder / "package.json").exists():
        command = f"npm run dev -- --port {port} --host 127.0.0.1"
    else:
        command = f"python3 -m http.server {port}"
    url = f"http://127.0.0.1:{port}"
    pid = 0
    try:
        process = subprocess.Popen(command, cwd=folder, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = process.pid
    except OSError:
        pass
    db.put("preview", run.get("projectId") or run["id"], {"pid": pid, "url": url})
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
    track = db.get("run-track", run["id"]) or {"loadedSkills": []}
    loaded = list(track.get("loadedSkills") or [])
    if skill["name"] in loaded:
        return {"output": "already loaded", "skill": skill["name"], "alreadyLoaded": True}
    if folder is not None:
        target = folder / ".skills" / skill["name"]
        target.mkdir(parents=True, exist_ok=True)
        for skill_file in skill.get("files") or []:
            path = sandbox.guard_path(target, skill_file.get("path") or "skill.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skill_file.get("content") or "")
        (target / "SKILL.md").write_text(skill.get("body") or "")
    loaded.append(skill["name"])
    track["loadedSkills"] = loaded
    db.put("run-track", run["id"], track)
    db.append_event(run["id"], "SKILL_LOADED", {"name": skill["name"]})
    body = (skill.get("body") or "").strip()
    return {"output": body or f"loaded skill: {skill['name']}", "skill": skill["name"]}


def _create_task(run: dict, arguments: dict) -> dict:
    project = db.get("project", run.get("projectId"))
    if project is None:
        return {"refused": True, "reason": "no project"}
    criteria = arguments.get("acceptanceCriteria") or arguments.get("criteria") or []
    if isinstance(criteria, str):
        criteria = [line.strip() for line in criteria.split("\n") if line.strip()]
    task = {
        "id": db.nid("task"),
        "projectId": project["id"],
        "parentTaskId": arguments.get("parentTaskId") or run.get("taskId"),
        "text": arguments.get("text") or "",
        "assignedAgentId": arguments.get("assignToAgentId") or "",
        "routedBy": "agent",
        "status": "planned",
        "summary": None,
        "diffRef": None,
        "screenshotRefs": [],
        "label": "task",
        "order": int(arguments.get("order") or 0),
        "acceptanceCriteria": list(criteria),
        "createdAt": db.now(),
    }
    if not task["assignedAgentId"]:
        route_task.route_task(project, task)
        task["routedBy"] = "agent"
    db.put("task", task["id"], task)
    track = db.get("run-track", run["id"]) or {}
    created = list(track.get("createdTaskIds") or [])
    created.append(task["id"])
    track["createdTaskIds"] = created
    db.put("run-track", run["id"], track)
    return {"output": task["id"], "taskId": task["id"]}


def _review(run: dict, arguments: dict) -> dict:
    from runtime import lead as leadlib

    return leadlib.apply_review(run, arguments.get("verdict") or "", arguments.get("notes") or "", arguments.get("items"))


def call_hash(name: str, arguments: dict) -> str:
    raw = json.dumps({"name": name, "arguments": arguments}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def stop_preview(project_id: str) -> None:
    record = db.get("preview", project_id)
    if not record:
        return
    try:
        pid = int(record.get("pid") or 0)
        if pid > 1:
            os_kill(pid)
    except (ProcessLookupError, PermissionError, OSError):
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
