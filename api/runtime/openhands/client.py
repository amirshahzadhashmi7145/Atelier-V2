"""OpenHands process adapter. Keys stay in the child environment only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from gateway import keys

PINNED = "1.51.0"
SERVER_IMAGE = os.environ.get("OPENHANDS_SERVER_IMAGE") or f"ghcr.io/openhands/agent-server:{PINNED}-python"
DRIVER = Path(__file__).resolve().parent / "driver.py"
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"


@dataclass
class RunSpec:
    workspace: Path
    prompt: str
    model: str
    api_key: str | None
    mcp: dict
    timeout_sec: int
    on_cost: Callable[[float], None] | None = None


@dataclass
class RunResult:
    events: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    summary: str = ""
    questions: list[str] = field(default_factory=list)
    blocked: bool = False


class OpenHandsClient(Protocol):
    def run(self, spec: RunSpec) -> RunResult: ...

    def cleanup(self) -> None: ...


_factory: Callable[[], OpenHandsClient] | None = None


def set_client_factory(factory: Callable[[], OpenHandsClient] | None) -> None:
    global _factory
    _factory = factory


def get_client() -> OpenHandsClient:
    if _factory is not None:
        return _factory()
    return ProcessOpenHandsClient()


class FakeOpenHands:
    """In-process stand-in used by mocked tests. Never talks to Docker or a model."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        packages: dict[str, str] | None = None,
        break_build: bool = False,
        cost_usd: float = 0.02,
        questions: list[str] | None = None,
        events: list[dict] | None = None,
        error: str | None = None,
        summary: str = "Finished the task in the sandbox.",
        leak_key_in: str | None = None,
    ):
        self.files = files or {}
        self.packages = packages or {}
        self.break_build = break_build
        self.cost_usd = cost_usd
        self.questions = questions or []
        self.events = events or [{"type": "action", "action": "write"}]
        self.error = error
        self.summary = summary
        self.leak_key_in = leak_key_in
        self.last_spec: RunSpec | None = None
        self.cleaned = False

    def run(self, spec: RunSpec) -> RunResult:
        self.last_spec = spec
        if spec.on_cost:
            spec.on_cost(self.cost_usd)
        if self.error:
            raise RuntimeError(self.error)
        folder = spec.workspace
        for rel, text in self.files.items():
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if self.packages:
            manifest = folder / "package.json"
            data: dict = {"name": "app", "private": True, "scripts": {"build": "node -e \"process.exit(0)\"", "test": "node -e \"process.exit(0)\""}, "dependencies": {}}
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text())
                except json.JSONDecodeError:
                    pass
            deps = dict(data.get("dependencies") or {})
            deps.update(self.packages)
            data["dependencies"] = deps
            manifest.write_text(json.dumps(data, indent=2))
        if self.break_build:
            manifest = folder / "package.json"
            data = {}
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text())
                except json.JSONDecodeError:
                    data = {}
            scripts = dict(data.get("scripts") or {})
            scripts["test"] = "node -e \"process.exit(1)\""
            scripts.setdefault("build", "node -e \"process.exit(0)\"")
            data["scripts"] = scripts
            data.setdefault("name", "app")
            manifest.write_text(json.dumps(data, indent=2))
        events = list(self.events)
        if self.leak_key_in == "event" and spec.api_key:
            events.append({"type": "note", "content": spec.api_key})
        if self.leak_key_in == "file" and spec.api_key:
            (folder / "leaked-key.txt").write_text(spec.api_key)
        return RunResult(
            events=events,
            cost_usd=self.cost_usd,
            summary=self.summary,
            questions=list(self.questions),
            blocked=bool(self.questions),
        )

    def cleanup(self) -> None:
        self.cleaned = True


class ProcessOpenHandsClient:
    """Run the pinned SDK in an isolated uv process with a Docker sandbox."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._cleaned = False

    def run(self, spec: RunSpec) -> RunResult:
        payload = {
            "workspace": str(spec.workspace),
            "prompt": spec.prompt,
            "model": spec.model,
            "mcp": spec.mcp,
            "timeout_sec": spec.timeout_sec,
            "server_image": SERVER_IMAGE,
        }
        env = {key: value for key, value in os.environ.items() if key != "LLM_API_KEY"}
        if spec.api_key:
            env["LLM_API_KEY"] = spec.api_key
        env["LLM_MODEL"] = spec.model
        cmd = [
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with-requirements",
            str(REQUIREMENTS),
            "python",
            str(DRIVER),
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(spec.workspace),
        )
        try:
            stdout, stderr = self._proc.communicate(json.dumps(payload), timeout=spec.timeout_sec + 60)
        except subprocess.TimeoutExpired:
            self.cleanup()
            raise TimeoutError("OpenHands exceeded the run time limit")
        if spec.api_key:
            stdout = keys.redact(stdout.replace(spec.api_key, keys.mask(spec.api_key) or "••••"))
            stderr = keys.redact(stderr.replace(spec.api_key, keys.mask(spec.api_key) or "••••"))
        events, result = _parse_jsonl(stdout)
        if self._proc.returncode not in (0, None) and not result:
            raise RuntimeError(keys.redact(stderr.strip() or stdout.strip() or "OpenHands process failed"))
        cost = float(result.get("costUsd") or 0)
        if spec.on_cost:
            spec.on_cost(cost)
        questions = [str(item) for item in (result.get("questions") or []) if str(item).strip()]
        return RunResult(
            events=events,
            cost_usd=cost,
            summary=str(result.get("summary") or ""),
            questions=questions,
            blocked=bool(result.get("blocked") or questions),
        )

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _parse_jsonl(text: str) -> tuple[list[dict], dict]:
    events: list[dict] = []
    result: dict = {}
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            events.append({"type": "log", "text": keys.redact(raw)})
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "result":
            result = item
        else:
            events.append(item)
    return events, result


def docker_available() -> bool:
    return shutil.which("docker") is not None
