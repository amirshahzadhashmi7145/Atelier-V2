"""OpenAI Chat Completions (and Ollama via OpenAI-compatible API)."""

from __future__ import annotations

import json
import os
import queue
import threading
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
        if self.id == "ollama":
            import urllib.request

            base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip().removesuffix("/v1")
            payload = json.loads(urllib.request.urlopen(f"{base}/api/tags", timeout=5).read())
            return [item["name"] for item in payload.get("models", [])]
        return [item.id for item in self._client().models.list()]

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
        if stream:
            yield from self._live_stream(model, messages, tools, config, tool_choice)
        else:
            turn = self._sync(model, messages, tools, config, tool_choice)
            yield {"kind": "done", **turn}

    def _mock_stream(self, messages: list[dict], stream: bool) -> Iterator[dict]:
        if os.environ.get("MOCK_MODEL_HANG") == "1":
            limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or str(FIRST_TOKEN_S))
            time.sleep(limit + 0.05)
            raise ModelTimeout("Model call timed out waiting for the first token.")
        mock_turns.PROMPTS.append(messages)
        turn = mock_turns.next_mock(messages)
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        if turn.get("deltas"):
            for piece in turn["deltas"]:
                yield {"kind": "delta", "text": piece["text"], "call": piece.get("call"), "index": piece.get("index")}
            yield self._done(turn, usage)
            return
        text = turn.get("content") or ""
        if stream and text:
            for index, word in enumerate(text.split(" ")):
                if not word:
                    continue
                piece = word if index == len(text.split(" ")) - 1 else word + " "
                yield {"kind": "delta", "text": piece}
        yield self._done(turn, usage)

    def _done(self, turn: dict, usage: dict) -> dict:
        return {
            "kind": "done",
            "content": turn.get("content") or "",
            "tool_calls": turn.get("tool_calls") or [],
            "usage": usage,
            "usd": mock_turns.usd(usage),
        }

    def _sync(self, model: str, messages: list[dict], tools: list[dict], config: dict, tool_choice: str | None) -> dict:
        kwargs: dict = {"model": self._model(model), "messages": messages}
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
            elif self.id == "ollama" and os.environ.get("OLLAMA_TOOL_CHOICE") == "required":
                kwargs["tool_choice"] = "required"
        self._apply_config(kwargs, config)
        response = self._client().chat.completions.create(**kwargs)
        choice = response.choices[0].message
        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }
        calls = []
        for call in choice.tool_calls or []:
            calls.append({"id": call.id, "name": call.function.name, "arguments": call.function.arguments})
        return {"content": choice.content or "", "tool_calls": calls, "usage": usage, "usd": mock_turns.usd(usage)}

    def _live_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        config: dict,
        tool_choice: str | None,
    ) -> Iterator[dict]:
        kwargs: dict = {"model": self._model(model), "messages": messages, "stream": True}
        if self.id == "openai":
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
            elif self.id == "ollama" and os.environ.get("OLLAMA_TOOL_CHOICE") == "required":
                kwargs["tool_choice"] = "required"
        self._apply_config(kwargs, config)
        pieces: list[str] = []
        calls: dict[int, dict] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        for chunk in self._stream_chunks(kwargs):
            if getattr(chunk, "usage", None):
                usage = {"input_tokens": chunk.usage.prompt_tokens or 0, "output_tokens": chunk.usage.completion_tokens or 0}
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                pieces.append(delta.content)
                yield {"kind": "delta", "text": delta.content}
            for tool in (delta.tool_calls or []) if delta else []:
                slot = calls.setdefault(tool.index or 0, {"id": "", "name": "", "arguments": ""})
                if tool.id:
                    slot["id"] = tool.id
                if tool.function and tool.function.name:
                    slot["name"] = tool.function.name
                if tool.function and tool.function.arguments:
                    slot["arguments"] += tool.function.arguments
        yield {
            "kind": "done",
            "content": "".join(pieces),
            "tool_calls": [calls[index] for index in sorted(calls)],
            "usage": usage,
            "usd": mock_turns.usd(usage),
        }

    def _stream_chunks(self, kwargs: dict):
        first_limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or str(FIRST_TOKEN_S))
        total_limit = float(os.environ.get("MODEL_TOTAL_S") or str(TOTAL_CALL_S))
        started = time.time()
        inbox: queue.Queue = queue.Queue()
        client = self._client()

        def pull() -> None:
            try:
                for chunk in client.chat.completions.create(**kwargs):
                    inbox.put(chunk)
                inbox.put(None)
            except Exception as exc:
                inbox.put(exc)

        threading.Thread(target=pull, daemon=True).start()
        saw_token = False
        while True:
            if time.time() - started > total_limit:
                raise ModelTimeout("Model call exceeded the total time limit.")
            wait = first_limit if not saw_token else min(30.0, total_limit - (time.time() - started))
            if wait <= 0:
                raise ModelTimeout("Model call exceeded the total time limit.")
            try:
                item = inbox.get(timeout=wait)
            except queue.Empty:
                if not saw_token:
                    raise ModelTimeout("Model call timed out waiting for the first token.")
                continue
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            if not saw_token and item.choices:
                delta = item.choices[0].delta
                if delta and (delta.content or delta.tool_calls):
                    saw_token = True
            yield item

    def _client(self):
        from openai import OpenAI

        if self.id == "ollama":
            base = os.environ.get("OLLAMA_BASE_URL", "").strip()
            if not base.endswith("/v1"):
                base = base.rstrip("/") + "/v1"
            return OpenAI(base_url=base, api_key=os.environ.get("OLLAMA_API_KEY") or "ollama")
        return OpenAI()

    def _model(self, name: str) -> str:
        if self.id == "ollama":
            return (os.environ.get("OLLAMA_MODEL") or name).strip()
        return name

    def _apply_config(self, kwargs: dict, config: dict) -> None:
        if "temperature" in config:
            kwargs["temperature"] = config["temperature"]
        if "maxOutputTokens" in config:
            key = "max_tokens" if self.id == "ollama" else "max_completion_tokens"
            kwargs[key] = config["maxOutputTokens"]
