"""Refuse an OpenHands run unless the isolated sidecar has the pinned litellm."""

from __future__ import annotations

import subprocess
from pathlib import Path

PINNED_LITELLM = "1.96.2"
ADVISORY = "GHSA-3cv6-jpf6-8222"
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"
LOCK = Path(__file__).resolve().parent / "requirements.lock"

_cached: str | None = None


class IsolatedLitellmMismatch(RuntimeError):
    def __init__(self, found: str):
        shown = found or "missing"
        super().__init__(
            f"isolated litellm is {shown}; pinned {PINNED_LITELLM} ({ADVISORY})"
        )
        self.found = found


def requirements_file() -> Path:
    return LOCK if LOCK.is_file() else REQUIREMENTS


def pinned_from_requirements() -> str:
    for line in REQUIREMENTS.read_text().splitlines():
        raw = line.strip()
        if raw.startswith("litellm=="):
            return raw.split("==", 1)[1].strip()
    return PINNED_LITELLM


def probe_isolated_version() -> str:
    global _cached
    if _cached is not None:
        return _cached
    cmd = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--with-requirements",
        str(requirements_file()),
        "python",
        "-c",
        "import litellm; print(litellm.__version__)",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    version = lines[-1] if lines else ""
    if version:
        _cached = version
    return version


def assert_pinned() -> str:
    expected = pinned_from_requirements()
    if expected != PINNED_LITELLM:
        raise IsolatedLitellmMismatch(expected)
    found = probe_isolated_version()
    if found != PINNED_LITELLM:
        raise IsolatedLitellmMismatch(found)
    return found
