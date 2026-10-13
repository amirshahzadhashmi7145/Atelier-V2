import json
import os
import re
import threading
import time
from pathlib import Path

from gateway import openai_gateway
from runtime import compile as compile_prompt
from runtime import tools
from store import db
from store import live

WAITS: dict[str, threading.Event] = {}


def wake(run_id: str) -> None:
    event = WAITS.get(run_id)
    if event:
        event.set()


def drive(run_id: str) -> None:
    run = db.get("run", run_id)
    if run is None:
        return
    workspace = db.get("workspace", run_id) or {}
    run["folder"] = workspace.get("folder")
    agent = db.get("agent", run["agentId"]) or {}
    settings = db.get("settings", "runs") or {}
    raw_cap = settings.get("maxSpendPerRunUsd")
    cap = float(5 if raw_cap is None else raw_cap)
    max_iterations = int(settings.get("maxIterations") or 60)
    max_minutes = int(settings.get("maxMinutes") or 45)
    detect_loops = settings.get("loopDetection", True)
    openai_gateway.begin()
    db.append_event(run_id, "RUN_STARTED", {})
    _status(run, "running")
    blocked = _blocked_framework(run, agent)
    if blocked:
        question = f"This task mentions {blocked}, which is not enabled for this agent. Enable it or rephrase?"
        if not _pause(run, "waiting_user", "CLARIFICATION_RAISED", {"question": question}):
            return
    started = time.time()
    hashes: list[str] = []
    unchanged = 0
    answer = None
    for _ in range(max_iterations):
        if _cancelled(run_id):
            return
        if time.time() - started > max_minutes * 60:
            _fail(run, "timeout", "The run exceeded the time limit.")
            return
        call_id = db.nid("call")
        turn = {"content": "", "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}, "usd": 0}
        opened: list[str] = []
        counts: dict[str, int] = {}
        for item in openai_gateway.stream_turn(
            run["model"]["name"],
            _messages(run, agent, answer),
            tools.openai_tools(agent),
            run["model"].get("config") or {},
        ):
            if item["kind"] == "delta":
                cid = item.get("call") or call_id
                if cid not in opened:
                    opened.append(cid)
                index = int(item["index"]) if item.get("index") else counts.get(cid, 0) + 1
                counts[cid] = max(counts.get(cid, 0), index)
                live.delta(run_id, cid, index, item["text"])
            else:
                turn = item
        if not opened:
            opened = [call_id]
        for cid in opened:
            text = live.finish(run_id, cid)
            if not text:
                text = turn.get("content") or ""
            db.append_event(run_id, "MODEL_OUTPUT", {"modelCallId": cid, "callId": cid, "text": text})
        answer = None
        usage = turn["usage"]
        cost = {"inputTokens": usage["input_tokens"], "outputTokens": usage["output_tokens"], "usd": turn["usd"]}
        db.append_event(run_id, "MODEL_CALLED", {}, cost)
        run["tokensIn"] += cost["inputTokens"]
        run["tokensOut"] += cost["outputTokens"]
        run["costUsd"] = round(run["costUsd"] + cost["usd"], 6)
        run["iterations"] += 1
        db.put("run", run_id, _public(run))
        if run["costUsd"] > cap:
            _fail(run, "budget", "The run exceeded the spend cap.")
            return
        calls = _calls(turn.get("tool_calls") or [])
        if not calls:
            continue
        for call in calls:
            if _cancelled(run_id):
                return
            digest = tools.call_hash(call["name"], call["arguments"])
            hashes.append(digest)
            if detect_loops and len(hashes) >= 3 and hashes[-3:] == [digest, digest, digest]:
                _fail(run, "loop", "The same tool call repeated.")
                return
            db.append_event(run_id, "TOOL_CALLED", {"name": call["name"], "arguments": call["arguments"]})
            result = tools.dispatch(run, call["name"], call["arguments"], lambda: _cancelled(run_id))
            if result.get("refused"):
                db.append_event(run_id, "TOOL_REFUSED", {"name": call["name"], "reason": result["reason"]})
                _say(run, f"{call['name']} was refused: {result['reason']}")
                continue
            if result.get("changed") is False:
                unchanged += 1
                if detect_loops and unchanged >= 2:
                    _fail(run, "loop", "Two edits changed nothing.")
                    return
            else:
                unchanged = 0
            if result.get("clarify"):
                questions = list(result.get("questions") or [result["clarify"]])[:3]
                record = db.get("clarify", run_id) or {"rounds": 0, "assumptions": []}
                if record["rounds"] >= 1:
                    assumption = "Proceeding with assumption: the earlier answer still stands."
                    record["assumptions"].append(assumption)
                    db.put("clarify", run_id, record)
                    db.append_event(run_id, "TOOL_RESULT", {"name": call["name"], "output": assumption})
                    continue
                record["rounds"] = 1
                db.put("clarify", run_id, record)
                if not _pause(run, "waiting_user", "CLARIFICATION_RAISED", {"question": "\n".join(questions), "questions": questions}):
                    return
                answer = (db.get("answer", run_id) or {}).get("text")
                continue
            if result.get("client"):
                if not _pause(run, "waiting_client", "CLIENT_TOOL_REQUESTED", {"requestId": result["requestId"], "prompt": result.get("prompt")}):
                    return
                continue
            if result.get("done"):
                _complete(run, result.get("summary") or {})
                return
            db.append_event(run_id, "TOOL_RESULT", {"name": call["name"], "output": _short(result.get("output"))})
    _fail(run, "timeout", "The run exceeded the iteration limit.")


def _blocked_framework(run: dict, agent: dict) -> str | None:
    stacks = {item["id"]: item for item in db.listing("stack")}
    enabled = " ".join((stacks.get(item) or {}).get("name", "") for item in agent.get("stackIds") or []).lower()
    for word in ("angular", "vue", "svelte", "solid", "remix", "astro", "nuxt"):
        if re.search(rf"\b{word}\b", run.get("task") or "", re.I) and word not in enabled:
            return word
    return None


def _calls(raw: list) -> list[dict]:
    parsed = []
    for call in raw:
        arguments = call.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        parsed.append({**call, "arguments": arguments})
    return parsed


def _messages(run: dict, agent: dict, answer: str | None) -> list[dict]:
    version = db.get("version", run.get("promptVersionId") or "") or _active_version(agent)
    compiled = version["compiled"] if version else compile_prompt.compile_prompt(agent.get("sections") or {}, agent.get("toolIds") or [], agent.get("skillIds") or [], agent.get("stackIds") or [])["compiled"]
    folder = Path(run["folder"]) if run.get("folder") else None
    tree = _tree(folder) if folder else ""
    skills = "\n".join(f"{item['name']}: {item['description']}" for item in db.listing("skill"))
    system = f"{compiled}\n\n# File tree\n{tree}\n\n# Skills index\n{skills}\n\n# Tools\n" + "\n".join(sorted(tools.allowed(agent)))
    task = db.get("task", run.get("taskId") or "") if run.get("taskId") else None
    tags = (agent.get("capabilities") or {}).get("tags") or []
    if task and "supervisor" in tags:
        system += f"\n\n# Work to review\n{task.get('summary') or ''}\n{task.get('diffRef') or ''}\n{', '.join(task.get('screenshotRefs') or [])}"
    messages = [{"role": "system", "content": system}]
    history = [item for item in db.listing("message") if item.get("projectId") == run.get("projectId")]
    history.sort(key=lambda item: item["createdAt"])
    project = db.get("project", run.get("projectId")) if run.get("projectId") else None
    if project and project.get("summary"):
        messages.append({"role": "user", "content": "Conversation so far: " + project["summary"]})
    for item in history[-20:]:
        messages.append({"role": "user" if item["role"] == "user" else "assistant", "content": item["text"]})
    messages.append({"role": "user", "content": run["task"]})
    if answer:
        messages.append({"role": "user", "content": answer})
    return messages


def _tree(folder: Path) -> str:
    lines = []
    for path in sorted(folder.rglob("*")):
        if ".git" in path.parts or "node_modules" in path.parts or len(lines) > 80:
            continue
        if path.is_file():
            lines.append(str(path.relative_to(folder)))
    return "\n".join(lines)


def _active_version(agent: dict):
    version_id = agent.get("activePromptVersionId")
    if not version_id:
        return None
    return db.get("version", version_id)


def _pause(run: dict, status: str, event_type: str, payload: dict) -> bool:
    _status(run, status)
    db.append_event(run["id"], event_type, payload)
    if event_type == "CLARIFICATION_RAISED" and run.get("projectId"):
        message_id = db.nid("msg")
        db.put(
            "message",
            message_id,
            {
                "id": message_id,
                "projectId": run["projectId"],
                "role": "agent",
                "text": payload.get("question") or "",
                "runId": run["id"],
                "createdAt": db.now(),
            },
        )
    event = threading.Event()
    WAITS[run["id"]] = event
    while not event.wait(0.2):
        if _cancelled(run["id"]):
            return False
    fresh = db.get("run", run["id"]) or run
    run.update({key: fresh[key] for key in fresh if key != "folder"})
    run["folder"] = (db.get("workspace", run["id"]) or {}).get("folder")
    return not _cancelled(run["id"])


def _complete(run: dict, summary: dict) -> None:
    summary = {
        "description": summary.get("description") or "Done.",
        "filesChanged": summary.get("filesChanged") or [item["path"] for item in (db.get("diff", run["id"]) or {"files": []})["files"]],
        "dependencies": summary.get("dependencies") or [],
        "criteria": summary.get("criteria") or [],
        "assumptions": [*(summary.get("assumptions") or []), *((db.get("clarify", run["id"]) or {}).get("assumptions") or [])],
        "followUps": summary.get("followUps") or [],
    }
    project = db.get("project", run.get("projectId")) if run.get("projectId") else None
    git = _publish(project, run) if project else {}
    if run.get("projectId") and run.get("folder"):
        preview = tools._preview(run, Path(run["folder"]))
        if preview.get("previewUrl"):
            git["previewUrl"] = preview["previewUrl"]
    run["summary"] = summary
    run["endedAt"] = db.now()
    run.update({key: value for key, value in git.items() if value})
    db.append_event(run["id"], "RUN_COMPLETED", {"summary": summary, **{key: value for key, value in git.items() if value}})
    run["status"] = "completed"
    db.put("run", run["id"], _public(run))
    if run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            task["status"] = "completed"
            task["summary"] = summary["description"]
            task["diffRef"] = run["id"]
            shots = [item["id"] for item in db.listing("artifact") if item.get("runId") == run["id"] and item.get("kind") == "screenshot"]
            task["screenshotRefs"] = shots
            db.put("task", task["id"], task)
    if project:
        reply = summary["description"]
        if git.get("prUrl"):
            reply = reply + "\n" + git["prUrl"]
        _say(run, reply)
        refresh_summary(project["id"], run["model"]["name"])


def _publish(project: dict, run: dict) -> dict:
    folder = Path(run["folder"]) if run.get("folder") else None
    if folder is None or not project.get("repoUrl") or not project.get("tokenRef"):
        return {}
    token = _token(project)
    if not token:
        return {}
    branch = f"task/{run.get('taskId') or run['id']}"
    _git(folder, ["checkout", "-B", branch])
    _git(folder, ["add", "-A"])
    _git(folder, ["commit", "-m", "Agent Studio task", "--allow-empty"])
    remote = _authed(project["repoUrl"], token)
    pushed = _git(folder, ["push", remote, f"HEAD:{branch}"])
    if token in pushed:
        pushed = pushed.replace(token, "***")
    pr = _pull_request(project["repoUrl"], token, branch, run["task"])
    return {"branch": branch, "prUrl": pr}


def _token(project: dict) -> str | None:
    ref = project.get("tokenRef") or ""
    if ref == "env:GITHUB_TOKEN":
        return os.environ.get("GITHUB_TOKEN")
    if ref.startswith("file:"):
        path = db.projects_dir() / ".secrets" / ref.removeprefix("file:")
        return path.read_text().strip() if path.exists() else None
    return None


def _authed(url: str, token: str) -> str:
    if url.startswith("https://github.com/"):
        return "https://x-access-token:" + token + "@" + url.removeprefix("https://")
    return url


def _pull_request(url: str, token: str, branch: str, title: str) -> str | None:
    slug = url.removeprefix("https://github.com/").removesuffix(".git")
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    repo = httpx.get(f"https://api.github.com/repos/{slug}", headers=headers, timeout=20)
    base = (repo.json().get("default_branch") if repo.status_code < 300 else None) or "main"
    response = httpx.post(
        f"https://api.github.com/repos/{slug}/pulls",
        headers=headers,
        json={"title": title[:80], "head": branch, "base": base},
        timeout=20,
    )
    if response.status_code >= 300:
        return None
    return response.json().get("html_url")


def _git(folder: Path, args: list[str]) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Agent Studio",
        "GIT_AUTHOR_EMAIL": "agent@localhost",
        "GIT_COMMITTER_NAME": "Agent Studio",
        "GIT_COMMITTER_EMAIL": "agent@localhost",
    }
    result = subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=folder, capture_output=True, text=True, env=env)
    return result.stdout + result.stderr


def _fail(run: dict, cause: str, text: str) -> None:
    run["terminalCause"] = cause
    run["endedAt"] = db.now()
    db.append_event(run["id"], "RUN_FAILED", {"cause": cause, "text": text})
    run["status"] = "failed"
    db.put("run", run["id"], _public(run))
    if run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            task["status"] = "failed"
            db.put("task", task["id"], task)
    _say(run, text)
    if run.get("projectId"):
        refresh_summary(run["projectId"], (run.get("model") or {}).get("name") or "gpt-4o")


def refresh_summary(project_id: str | None, model: str) -> None:
    if not project_id:
        return
    history = [item for item in db.listing("message") if item.get("projectId") == project_id]
    history.sort(key=lambda item: item["createdAt"])
    if len(history) <= 20:
        return
    older = "\n".join(f"{item['role']}: {item['text']}" for item in history[:-20])
    project = db.get("project", project_id)
    if project is None:
        return
    project["summary"] = openai_gateway.summarize(model, project.get("summary") or "", older)
    db.put("project", project_id, project)


def _say(run: dict, text: str) -> None:
    if not run.get("projectId") or not text:
        return
    message_id = db.nid("msg")
    db.put(
        "message",
        message_id,
        {"id": message_id, "projectId": run["projectId"], "role": "agent", "text": text, "runId": run["id"], "createdAt": db.now()},
    )


def _status(run: dict, status: str) -> None:
    run["status"] = status
    db.put("run", run["id"], _public(run))
    db.append_event(run["id"], "STATE_CHANGED", {"status": status})


def _cancelled(run_id: str) -> bool:
    try:
        fresh = db.get("run", run_id)
    except Exception:
        # ponytail: the database was reset under a live command, so stop
        return True
    return bool(fresh and fresh["status"] == "cancelled")


def _public(run: dict) -> dict:
    return {key: value for key, value in run.items() if key != "folder" and key != "answer"}


def _short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text[:2000]
