"""Google Gemini via google-genai (SDK stays in this module only)."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Iterator

from gateway import gemini_transcript, mock_turns
from gateway.exceptions import ModelTimeout, ProviderError
from gateway.tool_pairing import ToolPairingError, assert_chat_tool_pairing

FIRST_TOKEN_S = 60.0
TOTAL_CALL_S = 600.0
TEXT_MODEL = re.compile(r"^models/gemini|^gemini", re.I)
THINKING = re.compile(r"gemini-(2\.5-pro|3\.|thinking)", re.I)
BLOCKED = re.compile(r"embedding|tts|whisper|image|audio|veo|imagen", re.I)

TEMPERATURE = {"type": "number", "minimum": 0, "maximum": 2, "default": 0.2, "description": "Sampling temperature"}
MAX_OUTPUT = {"type": "integer", "minimum": 1, "maximum": 65536, "default": 8192, "description": "Maximum tokens to generate"}
THINKING_BUDGET = {
    "type": "integer",
    "minimum": 0,
    "maximum": 24576,
    "default": 8192,
    "description": "Thinking token budget (thinking-capable models)",
}
STRUCTURED = {"type": "boolean", "default": False, "description": "Require structured JSON outputs"}

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "gemini_recorded.json"

# Tests inspect the last contents list sent to the (mock) API.
last_contents_sent: list | None = None


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def provider_error_message(exc: Exception) -> str:
    from google.genai.errors import ClientError, ServerError

    if isinstance(exc, (ClientError, ServerError)):
        payload = getattr(exc, "response_json", None) or {}
        if isinstance(payload, dict):
            err = payload.get("error") or payload
            message = err.get("message") if isinstance(err, dict) else None
            status = err.get("status") if isinstance(err, dict) else None
            code = status or getattr(exc, "code", None)
            if message and code:
                return f"{code}: {message}"
            if message:
                return str(message)
        return str(payload) or str(exc)
    return str(exc)


class GeminiProvider:
    id = "gemini"

    def list_models(self) -> list[str]:
        if os.environ.get("GATEWAY_MOCK") == "1":
            return ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]
        names: list[str] = []
        for item in self._client().models.list():
            from app.models_catalog import is_chat, is_retired, model_id

            raw = model_id(item.name or "")
            if not raw or not is_chat(raw) or is_retired(raw):
                continue
            actions = item.supported_actions or []
            if actions and "generateContent" not in actions:
                continue
            if TEXT_MODEL.search(item.name or raw):
                names.append(raw)
        return sorted(set(names))

    def config_schema(self, model: str) -> dict:
        common = {"structuredOutputs": STRUCTURED}
        if THINKING.search(model):
            props = {"thinkingBudget": THINKING_BUDGET, "temperature": TEMPERATURE, **common}
        else:
            props = {"temperature": TEMPERATURE, "maxOutputTokens": MAX_OUTPUT, **common}
        return {"type": "object", "additionalProperties": False, "properties": props}

    def pricing(self, model: str) -> dict | None:
        return None

    def supported_config(self, model: str, config: dict) -> dict:
        """Drop keys the model's schema does not list (e.g. OpenAI leftovers like webSearch)."""
        allowed = self.config_schema(model)["properties"].keys()
        return {key: value for key, value in (config or {}).items() if key in allowed}

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
        assert_chat_tool_pairing(messages)
        gemini_transcript.assert_gemini_thought_signatures(messages)
        if os.environ.get("GATEWAY_MOCK") == "1":
            yield from self._mock_stream(messages, stream)
            return
        if stream:
            yield from self._live_stream(model, messages, tools, config)
        else:
            turn = self._collect(model, messages, tools, config)
            yield {"kind": "done", **turn}

    def _mock_stream(self, messages: list[dict], stream: bool) -> Iterator[dict]:
        if os.environ.get("MOCK_MODEL_HANG") == "1":
            limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or str(FIRST_TOKEN_S))
            time.sleep(limit + 0.05)
            raise ModelTimeout("Model call timed out waiting for the first token.")
        if os.environ.get("MOCK_GEMINI_PROVIDER_ERROR"):
            raise ProviderError(os.environ["MOCK_GEMINI_PROVIDER_ERROR"])
        if FIXTURE.is_file() and not mock_turns.SCRIPTS:
            payload = json.loads(FIXTURE.read_text())
            if payload.get("messages") == messages:
                recorded = payload.get("recorded") or {}
                for delta in recorded.get("deltas") or []:
                    yield {"kind": "delta", "text": delta.get("text") or ""}
                usage = recorded.get("usage") or {"input_tokens": 1, "output_tokens": 1}
                done = {
                    "kind": "done",
                    "content": recorded.get("content") or "",
                    "tool_calls": recorded.get("tool_calls_final") or recorded.get("tool_calls") or [],
                    "usage": usage,
                    "usd": mock_turns.usd(usage),
                    "gemini_model_content": recorded.get("gemini_model_content"),
                }
                yield done
                return
            second = payload.get("second_request") or {}
            if second.get("messages") == messages:
                _, contents = _to_gemini_contents(messages)
                global last_contents_sent
                last_contents_sent = contents
                recorded = second.get("recorded") or {}
                usage = recorded.get("usage") or {"input_tokens": 1, "output_tokens": 1}
                yield {
                    "kind": "done",
                    "content": recorded.get("content") or "ok",
                    "tool_calls": recorded.get("tool_calls") or [],
                    "usage": usage,
                    "usd": mock_turns.usd(usage),
                }
                return
        mock_turns.PROMPTS.append(messages)
        turn = mock_turns.next_mock(messages)
        usage = turn.get("usage", {"input_tokens": 10, "output_tokens": 10})
        text = turn.get("content") or ""
        if stream and text:
            yield {"kind": "delta", "text": text}
        yield {
            "kind": "done",
            "content": text,
            "tool_calls": turn.get("tool_calls") or [],
            "usage": usage,
            "usd": mock_turns.usd(usage),
            "gemini_model_content": turn.get("gemini_model_content"),
        }

    def _collect(self, model: str, messages: list[dict], tools: list[dict], config: dict) -> dict:
        turn = {"content": "", "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}, "usd": 0.0}
        for event in self._live_stream(model, messages, tools, config):
            if event["kind"] == "delta":
                turn["content"] += event.get("text") or ""
            elif event["kind"] == "done":
                turn = {k: v for k, v in event.items() if k != "kind"}
        return turn

    def _live_stream(self, model: str, messages: list[dict], tools: list[dict], config: dict) -> Iterator[dict]:
        from google.genai import types

        system, contents = _to_gemini_contents(messages)
        global last_contents_sent
        last_contents_sent = contents
        config = self.supported_config(model, config)
        # Gemini rejects a JSON response mime type together with function declarations.
        structured = bool(config.get("structuredOutputs")) and not tools
        gen_config = types.GenerateContentConfig(
            system_instruction=system or None,
            tools=_to_gemini_tools(tools) or None,
            temperature=config.get("temperature"),
            max_output_tokens=config.get("maxOutputTokens"),
            response_mime_type="application/json" if structured else None,
        )
        if THINKING.search(model):
            # Stream thought summaries: a large functionCall arrives as one part only when
            # fully generated, so without thoughts the first-token clock would see nothing.
            thinking = {"include_thoughts": True}
            if config.get("thinkingBudget") is not None:
                thinking["thinking_budget"] = int(config["thinkingBudget"])
            gen_config.thinking_config = types.ThinkingConfig(**thinking)

        pieces: list[str] = []
        calls: dict[int, dict] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        function_call_parts: list = []
        for chunk in self._stream_chunks(model, contents, gen_config):
            meta = getattr(chunk, "usage_metadata", None)
            if meta:
                usage = {
                    "input_tokens": meta.prompt_token_count or 0,
                    "output_tokens": meta.candidates_token_count or meta.total_token_count or 0,
                }
            if not chunk.candidates:
                continue
            candidate = chunk.candidates[0]
            parts = candidate.content.parts if candidate.content else []
            for part in parts or []:
                if getattr(part, "thought", False):
                    # Thought summary: activity for the first-token timer, not answer text.
                    yield {"kind": "thinking", "text": part.text or ""}
                    continue
                if part.text:
                    pieces.append(part.text)
                    yield {"kind": "delta", "text": part.text}
                if part.function_call:
                    fc = part.function_call
                    index = len(calls)
                    slot = calls.setdefault(
                        index,
                        {"id": fc.id or f"call_{index}", "name": fc.name or "", "arguments": ""},
                    )
                    args = fc.args
                    if args is not None:
                        slot["arguments"] = json.dumps(args) if isinstance(args, dict) else str(args)
                    # One stored part per call, in order. Parallel same-name calls stay separate.
                    function_call_parts.append(part)
                    yield {
                        "kind": "tool_delta",
                        "index": index,
                        "id": slot["id"],
                        "name": slot["name"],
                        "arguments": slot["arguments"],
                    }
        normalized = []
        for index in sorted(calls):
            call = calls[index]
            if isinstance(call.get("arguments"), dict):
                call["arguments"] = json.dumps(call["arguments"])
            normalized.append(call)
        gemini_model_content = None
        if function_call_parts or pieces:
            from google.genai import types

            model_parts: list[types.Part] = []
            text = "".join(pieces)
            if text:
                model_parts.append(types.Part(text=text))
            model_parts.extend(function_call_parts)
            gemini_model_content = gemini_transcript.dump_model_content(types.Content(role="model", parts=model_parts))
        yield {
            "kind": "done",
            "content": "".join(pieces),
            "tool_calls": normalized,
            "usage": usage,
            "usd": mock_turns.usd(usage),
            "gemini_model_content": gemini_model_content,
        }

    def _stream_chunks(self, model: str, contents, gen_config):
        first_limit = float(os.environ.get("MODEL_FIRST_TOKEN_S") or str(FIRST_TOKEN_S))
        total_limit = float(os.environ.get("MODEL_TOTAL_S") or str(TOTAL_CALL_S))
        started = time.time()
        inbox: queue.Queue = queue.Queue()
        client = self._client()
        model_id = model if model.startswith("models/") else f"models/{model}"

        def pull() -> None:
            try:
                for chunk in client.models.generate_content_stream(model=model_id, contents=contents, config=gen_config):
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
                raise ProviderError(provider_error_message(item)) from item
            if not saw_token:
                if item.candidates:
                    parts = item.candidates[0].content.parts if item.candidates[0].content else []
                    if any(
                        getattr(p, "thought", False) or getattr(p, "text", None) or getattr(p, "function_call", None)
                        for p in parts or []
                    ):
                        saw_token = True
            yield item

    def _client(self):
        from google import genai

        return genai.Client(api_key=api_key())


def _to_gemini_tools(tools: list[dict]):
    from google.genai import types

    decls = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not fn:
            continue
        decls.append(
            types.FunctionDeclaration(
                name=fn.get("name") or "",
                description=fn.get("description") or "",
                parameters_json_schema=fn.get("parameters") or {"type": "object", "properties": {}},
            )
        )
    if not decls:
        return None
    return [types.Tool(function_declarations=decls)]


def _to_gemini_contents(messages: list[dict]) -> tuple[str, list]:
    from google.genai import types

    system_parts: list[str] = []
    contents: list[types.Content] = []
    pending_calls: dict[str, str] = {}
    index = 0
    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        if role == "system":
            if message.get("content"):
                system_parts.append(str(message["content"]))
            index += 1
            continue
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=str(message.get("content") or ""))]))
            index += 1
            continue
        if role == "assistant":
            stored = message.get("gemini_model_content")
            if stored:
                contents.append(gemini_transcript.load_model_content(stored))
                for call in message.get("tool_calls") or []:
                    call_id = call.get("id") or ""
                    fn = call.get("function") if isinstance(call, dict) else {}
                    if call_id and fn.get("name"):
                        pending_calls[call_id] = fn.get("name")
                index += 1
                continue
            if message.get("tool_calls"):
                raise ToolPairingError("internal: thought_signature lost")
            parts: list[types.Part] = []
            if message.get("content"):
                parts.append(types.Part(text=str(message["content"])))
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
            index += 1
            continue
        if role == "tool":
            responses = []
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_message = messages[index]
                call_id = tool_message.get("tool_call_id") or ""
                name = tool_message.get("name") or pending_calls.get(call_id) or "tool"
                responses.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=name,
                            response={"result": tool_message.get("content") or ""},
                        )
                    )
                )
                index += 1
            if not responses:
                index += 1
                continue
            contents.append(types.Content(role="user", parts=responses))
            continue
        index += 1
    return "\n\n".join(system_parts), contents
