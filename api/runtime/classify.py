"""One cheap label before a run is created. The mock path is a word list so tests stay offline."""

import os
import re

from gateway import openai_gateway
from runtime import compile as compiler
from store import db

CONTROL_WORDS = ("stop", "wait", "cancel", "hold on")
FOLLOW_UP = re.compile(
    r"^(complete it|complete and run|run it|continue|finish|fix it|make it faster)\b",
    re.I,
)
PREVIEW_QUESTION = re.compile(
    r"\b(where.*(running|preview|url)|what url|preview url|which port|open the (app|preview))\b",
    re.I,
)
PREVIEW_WORD = r"pre(?:view|iew)"
PREVIEW_STOP = re.compile(
    rf"\b(stop|kill|close|end|shut\s*off|shut\s*down)\b.{{0,40}}\b{PREVIEW_WORD}\b|"
    rf"\b{PREVIEW_WORD}\b.{{0,24}}\b(stop|off)\b",
    re.I,
)
STACK_QUESTION = re.compile(
    r"\b(what|which|with what)\b.*\b(stacks?|frameworks?|tech)\b|"
    r"\b(stacks?|frameworks?|tech)\b.*\b(work with|use|support|enabled|can you)\b|"
    r"\bwhat (tech|stacks?)\b",
    re.I,
)
RUN_CAPABILITIES = "In a run I can edit files, run build and tests, open a preview, and capture screenshots."


def is_control(text: str) -> bool:
    low = text.lower().strip()
    if is_preview_stop(low):
        return False
    return low in CONTROL_WORDS or any(low.startswith(word + " ") or low == word for word in CONTROL_WORDS)


def is_preview_stop(text: str) -> bool:
    return PREVIEW_STOP.search(text.strip()) is not None


def prior_context(project_id: str) -> dict | None:
    rows = sorted(
        [item for item in db.listing("message") if item.get("projectId") == project_id and item.get("taskId")],
        key=lambda item: item["createdAt"],
    )
    if not rows:
        return None
    last = db.get("task", rows[-1]["taskId"])
    if last is None:
        return None
    if last.get("status") not in ("failed", "running", "waiting", "completed"):
        return None
    run = next((item for item in db.listing("run") if item.get("taskId") == last["id"]), None)
    diff = db.get("diff", run["id"]) if run else None
    failure = None
    if run and run.get("status") == "failed":
        failure = next((item["payload"].get("text") for item in reversed(db.events_for(run["id"])) if item["type"] == "RUN_FAILED"), None)
    task_text = (last.get("text") or "").split("\n\nPrevious attempt failed:")[0].strip()
    if len(task_text) > 400:
        task_text = task_text[:400] + "…"
    return {
        "taskText": task_text,
        "summary": last.get("summary") or "",
        "diff": diff,
        "failure": failure,
        "priorRunId": run["id"] if run else None,
    }


def looks_like_task(agent: dict, text: str, project_id: str | None = None) -> bool:
    return _heuristic(agent, text, project_id) == "task"


def label(agent: dict, text: str, project_id: str | None = None) -> str:
    if is_preview_stop(text):
        return "chat"
    if is_control(text):
        return "control"
    if os.environ.get("GATEWAY_MOCK") == "1":
        return _heuristic(agent, text, project_id)
    scope = agent.get("scope") or {}
    if os.environ.get("OLLAMA_BASE_URL") or not (scope.get("does") or scope.get("neverDoes")):
        return _heuristic(agent, text, project_id)
    does = ", ".join(scope.get("does") or []) or "none"
    never = ", ".join(scope.get("neverDoes") or []) or "none"
    last = ""
    if project_id:
        ctx = prior_context(project_id)
        if ctx:
            last = f"Last task: {ctx['taskText']}\nStatus summary: {ctx.get('summary') or 'none'}"
    try:
        model = agent.get("model") or {}
        turn = openai_gateway.complete(
            model.get("name") or "gpt-4o",
            [
                {
                    "role": "user",
                    "content": (
                        "Label the message as exactly one word: chat, task, or out.\n"
                        "chat = greeting, question about the agent, or small talk.\n"
                        "task = work inside scope.does, including follow-ups like continue or fix it when a task exists.\n"
                        "out = work inside scope.neverDoes. Enabled stacks do not widen scope.\n"
                        f"Does: {does}\nNever does: {never}\n{last}\nMessage: {text}"
                    ),
                }
            ],
            [],
            {},
            provider=model.get("provider"),
        )
        word = (turn.get("content") or "task").strip().lower().split()
        found = word[0] if word else "task"
        return found if found in ("chat", "task", "out") else "task"
    except Exception:
        return _heuristic(agent, text, project_id)


def chat_system(agent: dict) -> str:
    version = db.get("version", agent.get("activePromptVersionId") or "") if agent.get("activePromptVersionId") else None
    sections = (version or {}).get("sections") or agent.get("sections") or {}
    body = compiler.compile_prompt(
        sections,
        agent.get("toolIds") or [],
        agent.get("skillIds") or [],
        agent.get("stackIds") or [],
        (agent.get("model") or {}).get("name") or "gpt-4o",
        agent.get("scope"),
        include_tools=False,
    )["compiled"]
    return f"{body}\n\n{RUN_CAPABILITIES}"


def preview_location_reply(project_id: str) -> str:
    preview = db.get("preview", project_id)
    url = (preview or {}).get("url")
    if url:
        return (
            f"The preview is running at {url}. "
            "In chat, open the Preview panel (right side on a wide window, or the Preview button on smaller screens)."
        )
    return (
        "No preview URL is saved for this project yet. "
        "From the project folder run `npm run dev` — Vite usually serves at http://127.0.0.1:5173."
    )


def chat_reply(agent: dict, text: str, project_id: str | None = None) -> str:
    if project_id and PREVIEW_QUESTION.search(text.strip()):
        return preview_location_reply(project_id)
    system = chat_system(agent)
    history = []
    if project_id:
        project = db.get("project", project_id)
        if project and project.get("summary"):
            history.append(f"Project summary: {project['summary']}")
        rows = sorted([item for item in db.listing("message") if item.get("projectId") == project_id], key=lambda item: item["createdAt"])
        history.extend(f"{item['role']}: {item['text']}" for item in rows[-5:])
    prompt = "\n".join(history + [text]) if history else text
    if os.environ.get("GATEWAY_MOCK") == "1":
        return _mock_chat(system, text, project_id)
    try:
        model = agent.get("model") or {}
        turn = openai_gateway.complete(
            model.get("name") or "gpt-4o",
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            [],
            {},
            provider=model.get("provider"),
        )
        body = (turn.get("content") or "").strip()
        if not body:
            raise RuntimeError("empty")
        return body
    except Exception:
        return _mock_chat(system, text, project_id)


def refusal(agent: dict, text: str = "") -> str:
    canned = _canned(agent)
    if os.environ.get("GATEWAY_MOCK") == "1":
        return _mock_refusal(agent)
    system = compiler.scope_block(agent.get("scope")) + "\nReply in one or two sentences. It is outside the role. Tell the user to add an agent for that role. Do not offer to do the work."
    try:
        model = agent.get("model") or {}
        turn = openai_gateway.complete(
            model.get("name") or "gpt-4o",
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            [],
            {},
            provider=model.get("provider"),
        )
        body = (turn.get("content") or "").strip()
        if not body:
            raise RuntimeError("empty")
        return body
    except Exception:
        return canned


def _canned(agent: dict) -> str:
    does = ", ".join((agent.get("scope") or {}).get("does") or []) or "work inside this role"
    return f"That is outside my role. I can do {does}. Add an agent for that role."


def _mock_refusal(agent: dict) -> str:
    never = ", ".join((agent.get("scope") or {}).get("neverDoes") or []) or "that work"
    return f"That is outside my role. I do not do {never}. Add an agent for that role."


def _mock_chat(system: str, text: str, project_id: str | None) -> str:
    low = text.lower().strip()
    if FOLLOW_UP.match(low) and project_id and prior_context(project_id):
        return "Starting a run to continue the task."
    if "node" in low:
        return "No. Add a Backend Engineer agent for Node."
    if "tech" in low or "stack" in low or "work with" in low:
        names = _stack_names(system)
        listed = ", ".join(names) if names else "no stacks"
        return f"I can work with {listed}."
    if "cannot" in low or "can't" in low:
        return RUN_CAPABILITIES
    return "Hello. I can answer questions here without starting a run."


def _stack_names(system: str) -> list[str]:
    names = []
    grab = False
    for line in system.splitlines():
        if line.startswith("# Enabled stacks"):
            grab = True
            continue
        if grab and line.startswith("#"):
            break
        if grab and line and not line.startswith("Do not"):
            names.append(line.split()[0])
    return names


def _heuristic(agent: dict, text: str, project_id: str | None) -> str:
    low = text.lower().strip()
    if is_preview_stop(low) or PREVIEW_QUESTION.search(low) or STACK_QUESTION.search(low):
        return "chat"
    words = low.split()
    first = words[0] if words else ""
    if first in {"hello", "hi", "hey", "thanks"} or low in {"how are you", "good morning"}:
        return "chat"
    if low.startswith("can you explain") or low.startswith("what is ") or low.startswith("how does "):
        return "chat"
    if low.startswith("can you") or low.startswith("what tech") or low.startswith("what can you"):
        return "chat"
    if project_id and FOLLOW_UP.match(low) and prior_context(project_id):
        return "task"
    from runtime import lead as leadlib

    never = [] if leadlib.is_lead(agent) else [item.lower() for item in (agent.get("scope") or {}).get("neverDoes") or []]
    hints = {
        "servers": ("backend", "nodejs", "node.js", "node server"),
        "databases": ("database", "postgres", "sql"),
        "api implementation": ("api implementation",),
        "auth backends": ("auth backend",),
        "infrastructure": ("kubernetes", "terraform", "infrastructure"),
    }
    for item in never:
        if item in low:
            return "out"
        for hint in hints.get(item, ()):
            if hint in low:
                return "out"
    if re.search(r"\b(create|build|implement|add|make|develop|write|fix|multiplayer|single[\s-]?player)\b", low):
        return "task"
    return "task"
