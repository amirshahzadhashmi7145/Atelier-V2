import re

BLOCKED = re.compile(r"embedding|tts|whisper|dall-e|moderation|realtime|image|audio", re.I)
REASONING = re.compile(r"^(o\d|gpt-5)([-.]|$)", re.I)
TEMPERATURE = {"type": "number", "minimum": 0, "maximum": 2, "default": 0.2, "description": "Sampling temperature"}
MAX_OUTPUT = {"type": "integer", "minimum": 1, "maximum": 128000, "default": 4096, "description": "Maximum tokens to generate"}
EFFORT = {
    "type": "string",
    "enum": ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    "default": "medium",
    "description": "How hard the model thinks",
}
WEB = {"type": "boolean", "default": False, "description": "Allow the model to search the web"}
STRUCTURED = {"type": "boolean", "default": False, "description": "Require a JSON schema response"}


def is_chat(name: str) -> bool:
    return BLOCKED.search(name) is None


def reasoning(name: str) -> bool:
    return "chat" not in name.lower() and REASONING.search(name) is not None


def config_schema(name: str) -> dict:
    common = {"webSearch": WEB, "structuredOutputs": STRUCTURED}
    if reasoning(name):
        properties = {"maxOutputTokens": MAX_OUTPUT, "reasoningEffort": EFFORT, **common}
    elif re.match(r"^(gpt-|chatgpt-)", name, re.I):
        properties = {"temperature": TEMPERATURE, "maxOutputTokens": MAX_OUTPUT, **common}
    else:
        properties = common
    return {"type": "object", "additionalProperties": False, "properties": properties}


def speed(name: str) -> str:
    if re.search(r"mini|nano", name, re.I):
        return "fast"
    if re.match(r"^o\d", name, re.I):
        return "slow"
    return "balanced"


def seed_tags(name: str) -> dict:
    if re.search(r"mini|nano|fast", name, re.I):
        return {"tags": ["cheap", "fast"], "note": "heuristic, edit me", "heuristic": True}
    if reasoning(name):
        return {"tags": ["planning", "review"], "note": "heuristic, edit me", "heuristic": True}
    return {"tags": [], "note": "", "heuristic": False}


def info(name: str, provider: str | None = None) -> dict:
    from gateway.providers import registry

    pid = provider or ("gemini" if name.lower().startswith("gemini") else "openai")
    impl = registry.get(pid)
    schema = impl.config_schema(name)
    pricing = impl.pricing(name) or {}
    price_in = pricing.get("priceInPerM")
    price_out = pricing.get("priceOutPerM")
    benchmarks = pricing.get("benchmarks") or []
    if benchmarks and not all(entry.get("sourceUrl") for entry in benchmarks):
        benchmarks = []
    return {
        "provider": pid,
        "name": name,
        "contextWindow": pricing.get("contextWindow") or 128000,
        "priceInPerM": price_in if pricing.get("sourceUrl") else None,
        "priceOutPerM": price_out if pricing.get("sourceUrl") else None,
        "speedTier": speed(name),
        "fitLine": pricing.get("fitLine"),
        "configSchema": schema,
        "benchmarks": benchmarks,
    }
