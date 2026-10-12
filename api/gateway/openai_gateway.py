"""OpenAI calls live here and nowhere else."""

import os

# Tests push scripted turns here. Each turn is a dict with content, tool_calls, usage.
SCRIPTS: list[dict] = []

# ponytail: the models list has no context window or price
PRICE_IN = 2.5
PRICE_OUT = 10.0


def usd(usage: dict) -> float:
    return round((usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000, 6)


def complete(model: str, messages: list[dict], tools: list[dict], config: dict) -> dict:
    if os.environ.get("GATEWAY_MOCK") == "1":
        turn = SCRIPTS.pop(0) if SCRIPTS else _default_turn()
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        return {**turn, "usage": usage, "usd": usd(usage)}
    from openai import OpenAI

    kwargs: dict = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    if "temperature" in config:
        kwargs["temperature"] = config["temperature"]
    if "maxOutputTokens" in config:
        kwargs["max_completion_tokens"] = config["maxOutputTokens"]
    response = OpenAI().chat.completions.create(**kwargs)
    choice = response.choices[0].message
    usage = {
        "input_tokens": response.usage.prompt_tokens if response.usage else 0,
        "output_tokens": response.usage.completion_tokens if response.usage else 0,
    }
    calls = []
    for call in choice.tool_calls or []:
        calls.append({"id": call.id, "name": call.function.name, "arguments": call.function.arguments})
    return {"content": choice.content or "", "tool_calls": calls, "usage": usage, "usd": usd(usage)}


def list_model_ids() -> list[str]:
    if os.environ.get("GATEWAY_MOCK") == "1":
        return ["gpt-5", "gpt-4.1", "gpt-4.1-mini"]
    from openai import OpenAI

    return [item.id for item in OpenAI().models.list()]


_defaults = 0


def _default_turn() -> dict:
    global _defaults
    _defaults += 1
    if _defaults == 1:
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_write",
                    "name": "files",
                    "arguments": {
                        "op": "write",
                        "path": "index.html",
                        "content": "<h1>Hero</h1><section>One</section><section>Two</section><section>Three</section>",
                    },
                }
            ],
        }
    return {
        "content": "",
        "tool_calls": [
            {
                "id": "call_done",
                "name": "complete",
                "arguments": {
                    "summary": {
                        "description": "Landing page with a hero and three feature cards.",
                        "filesChanged": ["index.html"],
                        "dependencies": [],
                        "criteria": [],
                        "assumptions": [],
                        "followUps": [],
                    }
                },
            }
        ],
    }
