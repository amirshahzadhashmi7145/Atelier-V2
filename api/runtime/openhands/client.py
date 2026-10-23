"""OpenHands process adapter. Keys stay in the child environment only."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from gateway import keys
from runtime.openhands.envcheck import assert_pinned, requirements_file

PINNED = "1.51.0"
SERVER_IMAGE = os.environ.get("OPENHANDS_SERVER_IMAGE") or f"ghcr.io/openhands/agent-server:{PINNED}-python"
DRIVER = Path(__file__).resolve().parent / "driver.py"
_LIVE: list["ProcessOpenHandsClient"] = []
_LIVE_LOCK = threading.Lock()


def cleanup_live_clients() -> None:
    with _LIVE_LOCK:
        clients = list(_LIVE)
        _LIVE.clear()
    for client in clients:
        try:
            client.cleanup()
        except Exception:
            pass


@dataclass
class RunSpec:
    workspace: Path
    prompt: str
    model: str
    api_key: str | None
    mcp: dict
    timeout_sec: int
    on_cost: Callable[[float], None] | None = None
    on_event: Callable[[dict], None] | None = None
    repo_instructions: str = ""
    backup_model: str = ""
    backup_api_key: str | None = None
    thinking_budget: int | None = None


@dataclass
class RunResult:
    events: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    summary: str = ""
    questions: list[str] = field(default_factory=list)
    blocked: bool = False
    backup_used: bool = False
    actual_model: str = ""


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
        if spec.on_event:
            for item in events:
                spec.on_event(item)
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
        assert_pinned()
        payload = {
            "workspace": str(spec.workspace),
            "prompt": spec.prompt,
            "model": spec.model,
            "mcp": spec.mcp,
            "timeout_sec": spec.timeout_sec,
            "server_image": SERVER_IMAGE,
            "repo_instructions": spec.repo_instructions or "",
            "thinking_budget": spec.thinking_budget,
        }
        env = {key: value for key, value in os.environ.items() if key != "LLM_API_KEY"}
        env["OPENHANDS_SUPPRESS_BANNER"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        if spec.api_key:
            env["LLM_API_KEY"] = spec.api_key
        env["LLM_MODEL"] = spec.model
        if spec.backup_model:
            env["LLM_BACKUP_MODEL"] = spec.backup_model
        if spec.backup_api_key:
            env["LLM_BACKUP_API_KEY"] = spec.backup_api_key
        elif "LLM_BACKUP_API_KEY" in env:
            del env["LLM_BACKUP_API_KEY"]
        cmd = [
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with-requirements",
            str(requirements_file()),
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
            bufsize=1,
            start_new_session=True,
        )
        with _LIVE_LOCK:
            if self not in _LIVE:
                _LIVE.append(self)
        err: list[str] = []

        def _drain_err() -> None:
            proc = self._proc
            if proc and proc.stderr:
                err.append(proc.stderr.read() or "")

        threading.Thread(target=_drain_err, daemon=True).start()
        finished = threading.Event()

        def _kill_later() -> None:
            if finished.wait(spec.timeout_sec + 60):
                return
            self.cleanup()

        threading.Thread(target=_kill_later, daemon=True).start()
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.write(json.dumps(payload))
            self._proc.stdin.close()
            events, result = _iter_jsonl(self._proc.stdout, spec.on_event, spec.on_cost)
            self._proc.wait(timeout=30)
        except Exception:
            self.cleanup()
            raise
        finally:
            finished.set()
        if self._cleaned and not result:
            raise TimeoutError("OpenHands exceeded the run time limit")
        stdout = ""
        stderr = err[0] if err else ""
        for secret in (spec.api_key, spec.backup_api_key):
            if secret:
                stderr = keys.redact(stderr.replace(secret, keys.mask(secret) or "••••"))
        if result.get("error"):
            raise RuntimeError(keys.redact(str(result["error"])))
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
            backup_used=bool(result.get("backupUsed")),
            actual_model=str(result.get("actualModel") or spec.model),
        )

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        with _LIVE_LOCK:
            if self in _LIVE:
                _LIVE.remove(self)
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass


def _iter_jsonl(
    lines,
    on_event: Callable[[dict], None] | None = None,
    on_cost: Callable[[float], None] | None = None,
) -> tuple[list[dict], dict]:
    events: list[dict] = []
    result: dict = {}
    for line in lines or []:
        raw = (line if isinstance(line, str) else str(line)).strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            item = {"type": "log", "text": keys.redact(raw)}
        if not isinstance(item, dict):
            continue
        if item.get("type") == "result":
            result = item
            continue
        if item.get("type") == "cost":
            if on_cost:
                try:
                    on_cost(float(item.get("costUsd") or 0))
                except (TypeError, ValueError):
                    pass
            continue
        events.append(item)
        if on_event:
            on_event(item)
    return events, result


def _parse_jsonl(text: str) -> tuple[list[dict], dict]:
    return _iter_jsonl((text or "").splitlines())


def docker_available() -> bool:
    return shutil.which("docker") is not None
