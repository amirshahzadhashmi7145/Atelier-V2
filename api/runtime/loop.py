import json
import os
import subprocess
import re
import threading
import time
from pathlib import Path

from gateway import openai_gateway
from gateway.tool_pairing import ToolPairingError
from runtime import messages as msglib
from runtime import board, contract_file, lead as leadlib, members as memberlib, roles as rolelib
from runtime.scaffold import write_express_prisma, write_vite_react_ts
from runtime.tool_results import format_tool_result
from runtime import compile as compile_prompt
from runtime import sandbox, tools
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
    if run.get("kind") == "review":
        raw_cap = settings.get("maxSpendPerReviewUsd")
        cap = float(1 if raw_cap is None else raw_cap)
    else:
        raw_cap = settings.get("maxSpendPerRunUsd")
        cap = float(5 if raw_cap is None else raw_cap)
    max_iterations = int(settings.get("maxIterations") or 60)
    max_minutes = int(settings.get("maxMinutes") or 45)
    detect_loops = settings.get("loopDetection", True)
    openai_gateway.begin()
    db.append_event(run_id, "RUN_STARTED", {})
    _status(run, "running")
    blocked = None if run.get("kind") in ("lead", "review") or leadlib.is_lead(agent) else _blocked_framework(run, agent)
    if blocked:
        question = f"This task mentions {blocked}, which is not enabled for this agent. Enable it or rephrase?"
        if not _pause(run, "waiting_user", "CLARIFICATION_RAISED", {"question": question}):
            return
    started = time.time()
    unchanged = 0
    answer = None
    recent: list[str] = []
    last_key = None
    streak = 0
    note = None if run.get("kind") in ("lead", "review") or leadlib.is_lead(agent) else _prepare_scaffold(run, agent)
    if note:
        answer = note
    track = db.get("run-track", run_id) or _fresh_track()
    db.put("run-track", run_id, track)
    model_call_index = 0
    for _ in range(max_iterations):
        if _cancelled(run_id):
            return
        if time.time() - started > max_minutes * 60:
            _fail(run, "timeout", "The run exceeded the time limit.", recent)
            return
        call_id = db.nid("call")
        turn = {"content": "", "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}, "usd": 0}
        opened: list[str] = []
        counts: dict[str, int] = {}
        try:
            stream = openai_gateway.stream_turn(
                run["model"]["name"],
                _messages(run, agent, answer, track),
                tools.openai_tools(agent),
                run["model"].get("config") or {},
                run_id=run_id,
                call_index=model_call_index,
                provider=run["model"].get("provider"),
            )
            for item in stream:
                if item.get("kind") == "retry":
                    db.append_event(run_id, "MODEL_RETRY", {"attempt": item.get("attempt"), "reason": item.get("reason")})
                    continue
                if item.get("kind") == "thinking":
                    continue
                if item["kind"] == "delta":
                    cid = item.get("call") or call_id
                    if cid not in opened:
                        opened.append(cid)
                    index = int(item["index"]) if item.get("index") else counts.get(cid, 0) + 1
                    counts[cid] = max(counts.get(cid, 0), index)
                    live.delta(run_id, cid, index, item["text"])
                else:
                    turn = item
        except ToolPairingError as exc:
            _fail(run, "error", str(exc), recent)
            return
        except openai_gateway.ProviderError as exc:
            _fail(run, "error", exc.message, recent)
            return
        except openai_gateway.ModelTimeout as exc:
            _fail(run, "timeout", str(exc), recent)
            return
        model_call_index += 1
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
        openai_gateway.record_turn_cost(run, cost["usd"])
        run["iterations"] += 1
        if not _persist_run(run):
            return
        if run["costUsd"] > cap:
            message = "The review exceeded its spend cap." if run.get("kind") == "review" else "The run exceeded the spend cap."
            _fail(run, "budget", message, recent)
            return
        calls = _calls(turn.get("tool_calls") or [])
        if not calls:
            continue
        transcript = track.get("transcript") or []
        transcript.append(
            msglib.assistant_message(
                turn.get("content") or "",
                calls,
                gemini_model_content=turn.get("gemini_model_content"),
            )
        )
        for call in calls:
            if _cancelled(run_id):
                return
            db.append_event(run_id, "TOOL_CALLED", {"name": call["name"], "arguments": call["arguments"]})
            result = tools.dispatch(run, call["name"], call["arguments"], lambda: _cancelled(run_id))
            result_text = format_tool_result(call["name"], call["arguments"], result)
            transcript.append(msglib.tool_message(call["id"], result_text))
            recent.append(_plain(call))
            _note_tool(run_id, track, call, result)
            track["transcript"] = transcript
            db.put("run-track", run_id, track)
            if track.get("fail"):
                _fail(run, track.get("failCause") or "loop", track["fail"], recent)
                return
            if track.get("autoBuildNote"):
                answer = track.pop("autoBuildNote")
            if detect_loops:
                _read_only_repeat(track, call, result_text)
                nudge = track.pop("readOnlyNudge", None)
                if nudge:
                    answer = nudge
            if detect_loops and _repeatable(call):
                key = (tools.call_hash(call["name"], call["arguments"]), _short(result.get("reason") if result.get("refused") else result.get("output")))
                if key == last_key:
                    streak += 1
                else:
                    last_key = key
                    streak = 1
                if streak == 2:
                    answer = "you already ran this; change approach"
                if streak >= 3:
                    _fail(run, "loop", "the same tool call repeated", recent)
                    return
            if result.get("scopeEnd"):
                _fail(run, "error", result["reason"], recent)
                return
            if result.get("refused"):
                db.append_event(run_id, "TOOL_REFUSED", {"name": call["name"], "reason": result["reason"]})
                _say(run, f"{call['name']} was refused: {result['reason']}")
                continue
            if result.get("changed") is False:
                unchanged += 1
                if detect_loops and unchanged >= 2:
                    _fail(run, "loop", "Two edits changed nothing.", recent)
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
                track["transcript"] = transcript
                db.put("run-track", run_id, track)
                _complete(run, result.get("summary") or {})
                return
            db.append_event(run_id, "TOOL_RESULT", {"name": call["name"], "output": _short(result_text)})
        track["transcript"] = transcript
        db.put("run-track", run_id, track)
    _fail(run, "timeout", "The run exceeded the iteration limit.", recent)


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


def _fresh_track() -> dict:
    return {
        "transcript": [],
        "writesSinceBuild": 0,
        "fullWrites": {},
        "lastBuildOk": None,
        "loadedSkills": [],
        "staleTools": 0,
    }


def _read_only_repeat(track: dict, call: dict, result_text: str) -> None:
    args = call.get("arguments") or {}
    op = args.get("op") or "read"
    if call["name"] != "files" or op not in ("read", "list"):
        track["readOnlyStreak"] = 0
        return
    key = (tools.call_hash(call["name"], args), result_text[:500])
    if key == track.get("lastReadOnlyKey"):
        track["readOnlyStreak"] = int(track.get("readOnlyStreak") or 0) + 1
    else:
        track["readOnlyStreak"] = 1
        track["lastReadOnlyKey"] = key
    if track["readOnlyStreak"] == 2:
        track["readOnlyNudge"] = "you already ran this; change approach"



def _note_tool(run_id: str, track: dict, call: dict, result: dict) -> None:
    name = call["name"]
    args = call.get("arguments") or {}
    if name == "build_test":
        track["writesSinceBuild"] = 0
        track["lastBuildOk"] = result.get("buildOk")
        track["lastBuildReason"] = result.get("output")
        if result.get("buildOk"):
            track["staleTools"] = 0
        return
    if name == "load_skill" and not result.get("alreadyLoaded"):
        track["staleTools"] = 0
        return
    changed = result.get("changed")
    if name == "files":
        op = str(args.get("op") or "read")
        if op in ("read", "list"):
            return
        if op in ("write", "edit", "append") and changed:
            track["staleTools"] = 0
            track["writesSinceBuild"] = int(track.get("writesSinceBuild") or 0) + 1
            if op == "write" and result.get("fullWrite"):
                path = result.get("path") or args.get("path") or "file"
                counts = track.setdefault("fullWrites", {})
                counts[path] = int(counts.get(path) or 0) + 1
                if counts[path] == 2:
                    track["autoBuildNote"] = f"you rewrote {path}; use files.edit and run the build"
                if counts[path] >= 3:
                    track["fail"] = f"you rewrote {path} three times without editing"
                    track["failCause"] = "loop"
            if track["writesSinceBuild"] >= 3:
                run = db.get("run", run_id) or {}
                folder = Path(run["folder"]) if run.get("folder") else None
                built = tools._build(run, folder, lambda: False)
                track["writesSinceBuild"] = 0
                track["lastBuildOk"] = built.get("buildOk")
                track["lastBuildReason"] = built.get("output")
                track["autoBuildNote"] = f"Auto build_test: {built.get('output')}"
            return
    if changed is False and name == "files":
        return
    track["staleTools"] = int(track.get("staleTools") or 0) + 1
    if track["staleTools"] >= 15:
        track["fail"] = "no progress"
        track["failCause"] = "loop"


def _messages(run: dict, agent: dict, answer: str | None, track: dict | None = None) -> list[dict]:
    version = db.get("version", run.get("promptVersionId") or "") or _active_version(agent)
    compiled = version["compiled"] if version else compile_prompt.compile_prompt(agent.get("sections") or {}, agent.get("toolIds") or [], agent.get("skillIds") or [], agent.get("stackIds") or [], scope=agent.get("scope"))["compiled"]
    folder = Path(run["folder"]) if run.get("folder") else None
    tree = _tree(folder) if folder else ""
    skills = "\n".join(f"{item['name']}: {item['description']}" for item in db.listing("skill"))
    loaded = ", ".join((track or {}).get("loadedSkills") or []) or "none"
    system = f"{compiled}\n\n# File tree\n{tree}\n\n# Skills index\n{skills}\n\n# Loaded skills\n{loaded}\n\n# Tools\n" + "\n".join(sorted(tools.allowed(agent)))
    prior = run.get("priorContext")
    if prior:
        system += "\n\n# Prior task context\n"
        system += f"Task: {prior.get('taskText') or ''}\nSummary: {prior.get('summary') or ''}\n"
        if prior.get("failure"):
            system += f"Failure: {prior['failure']}\n"
        diff = prior.get("diff") or {}
        for item in (diff.get("files") or [])[:12]:
            system += f"Changed {item.get('path')}: { (item.get('after') or '')[:200]}\n"
    project = db.get("project", run.get("projectId")) if run.get("projectId") else None
    if run.get("kind") == "review":
        system += "\n\n" + leadlib.review_system(run, folder)
    elif leadlib.is_lead(agent) and project:
        system += "\n\n" + leadlib.lead_system(project, folder)
    else:
        contract = contract_file.contracts_for_reader(folder, agent)
        if contract:
            system += "\n\n# API contract\n" + contract
        if project:
            from runtime import notes

            system += "\n\n" + notes.for_prompt(project)
    task = db.get("task", run.get("taskId") or "") if run.get("taskId") else None
    if task and int(task.get("reworkCount") or task.get("reviewAttempts") or 0) > 0:
        packet = board.rework_packet(task)
        if packet:
            system += "\n\n" + packet
    prefix: list[dict] = []
    history = [item for item in db.listing("message") if item.get("projectId") == run.get("projectId")]
    history.sort(key=lambda item: item["createdAt"])
    project = project or (db.get("project", run.get("projectId")) if run.get("projectId") else None)
    if project and project.get("summary"):
        prefix.append({"role": "user", "content": "Conversation so far: " + project["summary"]})
    for item in history[-20:]:
        prefix.append({"role": "user" if item["role"] == "user" else "assistant", "content": item["text"]})
    prefix.append({"role": "user", "content": run["task"]})
    suffix: list[dict] = []
    if answer:
        suffix.append({"role": "user", "content": answer})
    transcript = (track or {}).get("transcript") or []
    return msglib.merge_system_and_transcript(system, transcript, prefix, suffix)

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


def _finish_run(run: dict) -> None:
    from runtime import project_runs

    if not run.get("projectId"):
        return
    if run.get("spendRecorded"):
        project_runs.drain(run["projectId"])
        return
    project_runs.add_spend(run["projectId"], float(run.get("costUsd") or 0))
    run["spendRecorded"] = True
    db.put("run", run["id"], _public(run))
    project_runs.drain(run["projectId"])


def _complete(run: dict, summary: dict) -> None:
    folder = Path(run["folder"]) if run.get("folder") else None
    agent = db.get("agent", run.get("agentId")) or {}
    project = db.get("project", run.get("projectId")) if run.get("projectId") else None
    skip_build = run.get("kind") in ("lead", "review") or leadlib.is_lead(agent)
    skip_preview = skip_build or bool(leadlib.lead_of(project or {}))
    if run.get("projectId") and folder is not None and (folder / "package.json").exists() and not skip_build:
        tools._build(run, folder, lambda: False)
        index = folder / "index.html"
        if index.exists():
            tools._browser(run, index.as_uri())
        if not skip_preview:
            tools._preview(run, folder)
    summary = {
        "description": summary.get("description") or "Done.",
        "filesChanged": summary.get("filesChanged") or [item["path"] for item in (db.get("diff", run["id"]) or {"files": []})["files"]],
        "dependencies": summary.get("dependencies") or [],
        "criteria": summary.get("criteria") or [],
        "assumptions": [*(summary.get("assumptions") or []), *((db.get("clarify", run["id"]) or {}).get("assumptions") or [])],
        "followUps": summary.get("followUps") or [],
        "endpoints": summary.get("endpoints") or [],
    }
    produced = rolelib.contract_file_of(agent)
    if produced and folder is not None:
        written = contract_file.write_contract(folder, summary, produced)
        if written and produced not in summary["filesChanged"]:
            summary["filesChanged"] = [*summary["filesChanged"], produced]
    git = _publish(project, run) if project else {}
    if run.get("projectId") and run.get("folder") and not skip_preview:
        preview = tools._preview(run, Path(run["folder"]))
        if preview.get("previewUrl"):
            git["previewUrl"] = preview["previewUrl"]
    run["summary"] = summary
    run["endedAt"] = db.now()
    run.update({key: value for key, value in git.items() if value})
    db.append_event(run["id"], "RUN_COMPLETED", {"summary": summary, **{key: value for key, value in git.items() if value}})
    run["status"] = "completed"
    db.put("run", run["id"], _public(run))
    if run.get("kind") == "review":
        _finish_run(run)
        return
    if run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            if run.get("kind") == "lead":
                leadlib.publish_plan(run)
            else:
                task["status"] = "completed"
                task["summary"] = summary["description"]
                task["diffRef"] = run["id"]
                shots = [item["id"] for item in db.listing("artifact") if item.get("runId") == run["id"] and item.get("kind") == "screenshot"]
                task["screenshotRefs"] = shots
                db.put("task", task["id"], task)
                if not leadlib.is_lead(agent):
                    board.write_handoff(run, task, summary)
    if project and run.get("kind") != "lead":
        reply = summary["description"]
        if git.get("prUrl"):
            reply = reply + "\n" + git["prUrl"]
        _say(run, reply)
        refresh_summary(project["id"], run["model"]["name"])
    elif project and run.get("kind") == "lead" and not children_waiting(run):
        reply = summary["description"]
        _say(run, reply)
    _finish_run(run)


def children_waiting(run: dict) -> bool:
    task_id = run.get("taskId")
    return bool(task_id and leadlib.children_of(task_id))


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


def _prepare_scaffold(run: dict, agent: dict) -> str | None:
    folder = Path(run["folder"]) if run.get("folder") else None
    if folder is None or not folder.is_dir() or _tree(folder).strip():
        return None
    stacks = {item["id"]: item for item in db.listing("stack")}
    for stack_id in agent.get("stackIds") or []:
        command = ((stacks.get(stack_id) or {}).get("scaffoldTemplate") or "").strip()
        if not command:
            continue
        if " " in command or command.startswith(("npm", "npx", "pnpm", "yarn")):
            try:
                code, _output = sandbox.run_command(folder, command, lambda: False)
            except PermissionError:
                continue
            if code != 0 and not _tree(folder).strip():
                continue
        else:
            # ponytail: template ids such as vite-react-ts are not shell commands; write a starter instead of an interactive CLI
            if command == "vite-react-ts":
                write_vite_react_ts(folder)
            elif command == "express-prisma":
                write_express_prisma(folder)
            else:
                _write_starter(folder)
        return f"The scaffold already exists ({command}). Do not run a create command."
    return None


def _write_starter(folder: Path) -> None:
    package = {"name": "app", "private": True, "scripts": {"build": "node -e \"process.exit(0)\"", "test": "node -e \"process.exit(0)\"", "dev": "vite"}}
    (folder / "package.json").write_text(json.dumps(package, indent=2))
    src = folder / "src"
    src.mkdir(exist_ok=True)
    (src / "main.tsx").write_text('export {}\n')
    (folder / "index.html").write_text("<!doctype html><html><body><div id=\"root\"></div></body></html>\n")
    (folder / "vite.config.ts").write_text("export default {}\n")


def _repeatable(call: dict) -> bool:
    name = call["name"]
    op = str((call.get("arguments") or {}).get("op") or "")
    if name in ("search_data", "load_skill"):
        return False
    if name == "files" and op in ("read", "list"):
        return False
    return name in ("files", "shell")


def _plain(call: dict) -> str:
    args = call.get("arguments") or {}
    if call["name"] == "files":
        op = str(args.get("op") or "read")
        path = args.get("path") or "a file"
        verb = {"read": "reading", "write": "writing", "edit": "editing", "list": "listing"}.get(op, op)
        return f"{verb} {path}"
    if call["name"] == "shell":
        return f"running {args.get('command') or 'a command'}"
    return f"using {call['name'].replace('_', ' ')}"


def _fail(run: dict, cause: str, text: str, recent: list[str] | None = None) -> None:
    doing = ", ".join((recent or [])[-3:]) or "starting the task"
    text = f"I was {doing}. Cause: {text}"
    run["terminalCause"] = cause
    run["endedAt"] = db.now()
    db.append_event(run["id"], "RUN_FAILED", {"cause": cause, "text": text})
    _say(run, text)
    run["status"] = "failed"
    db.put("run", run["id"], _public(run))
    if run.get("taskId"):
        task = db.get("task", run["taskId"])
        if task:
            task["status"] = "failed"
            db.put("task", task["id"], task)
    if run.get("projectId"):
        refresh_summary(run["projectId"], (run.get("model") or {}).get("name") or "gpt-4o")
    _finish_run(run)


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
    agent = db.get("agent", run.get("agentId")) or {}
    db.put(
        "message",
        message_id,
        {
            "id": message_id,
            "projectId": run["projectId"],
            "role": "agent",
            "text": text,
            "runId": run["id"],
            "createdAt": db.now(),
            **memberlib.stamp(agent),
        },
    )


def _persist_run(run: dict) -> bool:
    """Keep a user stop from being overwritten by the worker's in-memory copy."""
    fresh = db.get("run", run["id"]) or {}
    if fresh.get("status") == "cancelled" and run.get("status") != "cancelled":
        run["status"] = "cancelled"
        run["endedAt"] = fresh.get("endedAt") or run.get("endedAt")
        return False
    db.put("run", run["id"], _public(run))
    return True


def _status(run: dict, status: str) -> None:
    run["status"] = status
    if not _persist_run(run):
        return
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
