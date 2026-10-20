"""OpenAI mock streams and config schema. Live calls go through gateway.llm."""

from __future__ import annotations

import os
import time
from typing import Iterator

from gateway import mock_turns
from gateway.exceptions import ModelTimeout

FIRST_TOKEN_S = 60.0
TOTAL_CALL_S = 600.0


def _resolve_id(provider_id: str) -> str:
    return provider_id if provider_id in ("openai", "ollama") else "openai"


class OpenAIProvider:
    id: str

    def __init__(self, provider_id: str = "openai") -> None:
        self.id = _resolve_id(provider_id)

    def list_models(self) -> list[str]:
        if os.environ.get("GATEWAY_MOCK") == "1":
            if self.id == "ollama":
                return ["llama3.2:3b"]
            return ["gpt-5", "gpt-4.1", "gpt-4.1-mini"]
        from gateway.llm import list_live_models

        return list_live_models(self.id)

    def config_schema(self, model: str) -> dict:
        from app import models_catalog

        return models_catalog.config_schema(model)

    def pricing(self, model: str) -> dict | None:
        return None

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        config: dict,
        *,
        stream: bool = True,
        tool_choice: str | None = None,
    ) -> Iterator[dict]:
        if os.environ.get("GATEWAY_MOCK") == "1":
            yield from self._mock_stream(messages, stream)
            return
        from gateway.llm import iter_live_events

        yield from iter_live_events(
            self.id, model, messages, tools, config, stream=stream, tool_choice=tool_choice
        )

    def _mock_stream(self, messages: list[dict], stream: bool) -> Iterator[dict]:
        if os.environ.get("MOCK_MODEL_HANG") == "1":
            limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or str(FIRST_TOKEN_S))
            time.sleep(limit + 0.05)
            raise ModelTimeout("Model call timed out waiting for the first token.")
        mock_turns.PROMPTS.append(messages)
        turn = mock_turns.next_mock(messages)
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        pace = float(os.environ.get("STREAM_PACE_MS") or 0) / 1000
        if turn.get("deltas"):
            for piece in turn["deltas"]:
                yield {"kind": "delta", "text": piece["text"], "call": piece.get("call"), "index": piece.get("index")}
                if pace:
                    time.sleep(pace)
            yield self._done(turn, usage)
            return
        text = turn.get("content") or ""
        if stream and text:
            words = text.split(" ")
            for index, word in enumerate(words):
                if not word:
                    continue
                piece = word if index == len(words) - 1 else word + " "
                yield {"kind": "delta", "text": piece}
                if pace:
                    time.sleep(pace)
        yield self._done(turn, usage)

    def _done(self, turn: dict, usage: dict) -> dict:
        return {
            "kind": "done",
            "content": turn.get("content") or "",
            "tool_calls": turn.get("tool_calls") or [],
            "usage": usage,
            "usd": mock_turns.usd(usage),
        }
