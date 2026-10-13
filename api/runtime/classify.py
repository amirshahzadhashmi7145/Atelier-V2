"""One cheap label before a run is created. The mock path is a word list so tests stay offline."""

import os

from gateway import openai_gateway


def label(agent: dict, text: str) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        return _heuristic(agent, text)
    role = agent.get("roleKey") or agent.get("name") or "agent"
    stacks = ", ".join(agent.get("stackIds") or []) or "none"
    turn = openai_gateway.complete(
        (agent.get("model") or {}).get("name") or "gpt-4o",
        [
            {
                "role": "user",
                "content": (
                    "Label the message as exactly one word: chat, task, or out.\n"
                    "chat = greeting, question about the agent, or small talk.\n"
                    "task = work this role can do.\n"
                    "out = work outside the role or its enabled stacks.\n"
                    f"Role: {role}\nStacks: {stacks}\nMessage: {text}"
                ),
            }
        ],
        [],
        {},
    )
    word = (turn.get("content") or "task").strip().lower().split()
    found = word[0] if word else "task"
    return found if found in ("chat", "task", "out") else "task"


def chat_reply(agent: dict, text: str) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        return "Hello. I can answer questions here without starting a run."
    turn = openai_gateway.complete(
        (agent.get("model") or {}).get("name") or "gpt-4o",
        [{"role": "user", "content": "Reply in one or two sentences. Do not use tools.\n" + text}],
        [],
        {},
    )
    return (turn.get("content") or "Hello.").strip()


def refusal(agent: dict) -> str:
    from store import db

    role = agent.get("roleKey") or "this agent"
    names = []
    for stack_id in agent.get("stackIds") or []:
        stack = db.get("stack", stack_id)
        if stack:
            names.append(stack.get("name") or stack_id)
    enabled = ", ".join(names) if names else "none"
    return f"I can't do that. This agent is a {role}, and the enabled stacks are {enabled}. I can work inside that role."


def _heuristic(agent: dict, text: str) -> str:
    # ponytail: word list while GATEWAY_MOCK=1; the live path is one completion
    words = text.lower().strip().split()
    first = words[0] if words else ""
    if first in {"hello", "hi", "hey", "thanks"} or text.lower().strip() in {"how are you", "good morning"}:
        return "chat"
    role = (agent.get("roleKey") or "").lower()
    blob = text.lower()
    if role == "frontend" and any(token in blob for token in ("kubernetes", "terraform", "django", "python api")):
        return "out"
    return "task"
