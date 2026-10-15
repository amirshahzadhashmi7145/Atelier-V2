from __future__ import annotations

import os

from gateway.providers import gemini as gemini_mod
from gateway.providers import openai as openai_mod
from gateway.providers.base import ModelProvider


def resolve_provider(explicit: str | None) -> str:
    if explicit in ("openai", "ollama", "gemini"):
        return explicit
    if os.environ.get("OLLAMA_BASE_URL", "").strip():
        return "ollama"
    return "openai"


def get(provider: str | None = None) -> ModelProvider:
    pid = resolve_provider(provider)
    if pid == "gemini":
        return gemini_mod.GeminiProvider()
    return openai_mod.OpenAIProvider(pid if pid == "ollama" else "openai")
