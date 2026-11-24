"""Cursor-style "Auto" model selection.

An agent's model may be left as "auto" (the default). At the moment a run starts,
`resolve()` turns that into a concrete, currently-available model chosen for the
task's difficulty: supervisors, planning, reviews and clearly-hard tasks get a
stronger model; simple worker tasks get a fast, cheap one. It also rescues an
agent whose pinned model has been removed by the provider (e.g. a retired Gemini
model) by substituting an available one, so a stale default never crashes a run.

Selection never returns a retired/removed model, and it prefers a model the role
has actually done well on (runtime.fit) once there's enough evidence.
"""

from __future__ import annotations

import os
import re

from app import models_catalog
from gateway import llm
from store import db

AUTO = "auto"

# A small LLM classifier (routed to the cheapest available model) reads each worker
# task and decides whether it needs a powerful model — OpenHands-style task routing.
# Set ROUTER_CLASSIFIER=0 to fall back to the keyword heuristic only.
_CLASSIFIER_PROMPT = (
    "You route a coding task to the right model. Reply with ONE word: simple or complex.\n"
    "complex = multi-file or cross-cutting changes, architecture or API design, debugging, "
    "auth/security, performance/concurrency, tricky algorithms, or anything needing careful "
    "multi-step reasoning.\n"
    "simple = a small, localized change: a UI tweak, copy/text edit, single-file CRUD, config.\n"
    "Task:\n{text}"
)
# Cache decisions by task text so a task's retries don't re-classify. Bounded.
_DIFFICULTY_CACHE: dict[str, str] = {}

# Clearly-hard signals in a task description bump a worker task up a tier.
_HARD = re.compile(
    r"\b(architect\w*|refactor\w*|redesign|migrat\w+|concurren\w+|thread\s*safe|"
    r"security|auth\w*|encrypt\w+|performance|optimi[sz]e|scal\w+|algorithm|"
    r"race condition|complex|debug this|fix the failing|root cause)\b",
    re.I,
)
_STRONG = re.compile(r"\b(gpt-5|o\d|opus|pro)\b", re.I)
_FAST = re.compile(r"mini|nano|flash|lite|haiku|small", re.I)
# Experimental / preview / dated snapshots are less reliable for generateContent —
# only fall back to them when nothing stable is available.
_UNSTABLE = re.compile(r"experimental|preview|[-_]exp\b|[-_]exp[-_]|\b\d{4}-\d{2}-\d{2}\b|-\d{3,4}$", re.I)


def is_auto(spec: dict | None) -> bool:
    if not spec:
        return True
    name = (spec.get("name") or "").strip().lower()
    return name in ("", AUTO)


def auto_spec() -> dict:
    """The marker stored on an agent that wants Auto selection."""
    return {"provider": None, "name": AUTO, "config": {}}


def _provider(spec_provider: str | None) -> str:
    if spec_provider and spec_provider != AUTO:
        return spec_provider
    return (llm.default_model_spec().get("provider")) or "openai"


def _usable(ids: list[str]) -> list[str]:
    # is_chat drops blocked families (learnlm, gemma, embeddings, …) even from a stale
    # cache; name-based retirement drops explicitly-retired models. We do NOT apply
    # litellm's offline shutdown dates — they go stale and would wrongly remove current
    # models the provider still serves.
    live = [m for m in ids if models_catalog.is_chat(m) and not models_catalog.retired_by_name(m)]
    # Prefer stable models; only keep experimental/preview ones if nothing else exists.
    stable = [m for m in live if not _UNSTABLE.search(m)]
    return stable or live


def _has_stable(pool: list[str]) -> bool:
    return any(not _UNSTABLE.search(m) for m in pool)


def available(provider: str) -> list[str]:
    """Currently-available models for a provider. Reads the per-provider cache first
    (cheap); if it's missing, empty, or has nothing stable (e.g. a stale cache left with
    only removed/experimental models), re-queries the live API and re-caches."""
    cached = db.get("model-cache", provider) or {}
    pool = _usable(list(cached.get("ids") or []))
    if not _has_stable(pool):
        try:
            ids = llm.list_model_ids(provider) or []
        except Exception:
            ids = []
        if ids:
            db.put("model-cache", provider, {"ids": ids})
            pool = _usable(ids)
    return pool


def _fastest(pool: list[str]) -> str:
    """The cheapest/fastest usable model — used to run the routing classifier itself."""
    fast = [m for m in pool if _FAST.search(m) and not _STRONG.search(m.lower())]
    return sorted(fast or pool)[0]


def _heuristic_difficulty(text: str | None) -> str:
    return "complex" if (text and _HARD.search(text)) else "simple"


def classify_difficulty(text: str | None, provider: str, pool: list[str]) -> str:
    """Classify a task as "simple" or "complex" with a cheap LLM call (routed to the
    fastest available model). Falls back to the keyword heuristic offline/in mock mode,
    on error, or when disabled. Decisions are cached per task text."""
    body = (text or "").strip()
    if not body:
        return "simple"
    if os.environ.get("ROUTER_CLASSIFIER") == "0" or os.environ.get("GATEWAY_MOCK") == "1" or not pool:
        return _heuristic_difficulty(body)
    key = f"{provider}:{hash(body)}"
    cached = _DIFFICULTY_CACHE.get(key)
    if cached:
        return cached
    verdict = _heuristic_difficulty(body)
    try:
        from gateway import openai_gateway

        turn = openai_gateway.complete(
            _fastest(pool),
            [{"role": "user", "content": _CLASSIFIER_PROMPT.format(text=body[:1500])}],
            [],
            {},
            provider=provider,
        )
        word = (turn.get("content") or "").strip().lower()
        if word.startswith("complex"):
            verdict = "complex"
        elif word.startswith("simple"):
            verdict = "simple"
    except Exception:
        pass  # keep the heuristic verdict
    if len(_DIFFICULTY_CACHE) > 512:
        _DIFFICULTY_CACHE.clear()
    _DIFFICULTY_CACHE[key] = verdict
    return verdict


def tier_for(
    kind: str | None,
    role_key: str | None,
    text: str | None,
    *,
    provider: str | None = None,
    pool: list[str] | None = None,
) -> str:
    """"high" for work that needs stronger reasoning, else "standard".

    Supervisors, planning and reviews are always high. For a worker task, a cheap LLM
    classifier (when a provider/pool is available) decides whether the task is complex
    enough to warrant the stronger model; otherwise the keyword heuristic is used."""
    if (kind or "").lower() in ("lead", "review", "plan", "planning"):
        return "high"
    role = (role_key or "").lower()
    if any(word in role for word in ("lead", "qa", "review", "architect", "principal", "staff")):
        return "high"
    if provider and pool:
        return "high" if classify_difficulty(text, provider, pool) == "complex" else "standard"
    if text and _HARD.search(text):
        return "high"
    return "standard"


def _rank(names: list[str], tier: str) -> list[str]:
    def score(name: str) -> int:
        low = name.lower()
        strong = models_catalog.reasoning(name) or bool(_STRONG.search(low))
        fast = bool(_FAST.search(low))
        value = 0
        if _UNSTABLE.search(name):
            value -= 200  # experimental/preview/dated snapshots are a last resort
        if tier == "high":
            if strong:
                value += 100
            if "mini" in low or "nano" in low or "lite" in low:
                value -= 30
        else:  # standard: prefer fast & cheap, but a capable all-rounder beats a toy
            if fast:
                value += 50
            if strong and "mini" not in low and "nano" not in low:
                value += 15
        return value

    # Stable, deterministic: best score first, then name for ties.
    return sorted(names, key=lambda name: (-score(name), name))


def resolve(spec: dict | None, *, role_key: str | None = None, kind: str | None = None, text: str | None = None) -> dict | None:
    """Turn an agent's model spec into a concrete, available model for this task.

    - A pinned model that is still available is kept unchanged.
    - "auto" (or an unset model) is resolved to the best available model for the tier.
    - A pinned model the provider no longer offers is substituted with an available one.
    """
    base = models_catalog.normalize_spec(spec) or {}
    want_auto = is_auto(base)
    provider = _provider(base.get("provider"))
    pool = available(provider)

    if not want_auto:
        name = base.get("name") or ""
        # Keep the pinned model if the provider still offers it (it's in the live pool),
        # or — when we can't see a pool (offline) — if its name isn't marked retired.
        if name and not models_catalog.retired_by_name(name) and (name in pool or not pool):
            return base
        # Otherwise it's gone/removed: fall through and auto-pick for its provider.

    if not pool:
        # No list to choose from (offline / no key): the static default is the best we
        # can do, but make sure it isn't itself a retired model.
        fallback = llm.default_model_spec()
        return fallback

    tier = tier_for(kind, role_key, text, provider=provider, pool=pool)
    # A role that has proven itself on a specific available model wins.
    try:
        from runtime import fit

        suggested = fit.suggestion(role_key or "")
    except Exception:
        suggested = None
    if suggested and suggested.get("name") in pool and suggested.get("provider") == provider:
        name = suggested["name"]
    else:
        name = _rank(pool, tier)[0]
    return models_catalog.normalize_spec({"provider": provider, "name": name, "config": base.get("config") or {}})
