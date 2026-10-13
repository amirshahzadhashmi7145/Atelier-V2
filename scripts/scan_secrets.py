#!/usr/bin/env python3
"""Fail if a tracked file looks like it contains an API key. .env.example is tracked, so it is scanned."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", ".venv", "dist", ".next", "uv.lock"}
PREFIXES = ("sk" + "-", "ghp" + "_", "github_pat" + "_", "xoxb" + "-", "xoxp" + "-", "AKIA", "AIza")
PATTERN = re.compile("|".join(re.escape(item) + r"[A-Za-z0-9_\-]{8,}" for item in PREFIXES))


def scan(path: Path) -> list[str]:
    hits = []
    if not path.is_file():
        return hits
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return hits
    for number, line in enumerate(text.splitlines(), start=1):
        if PATTERN.search(line):
            hits.append(f"{path.relative_to(ROOT)}:{number}")
    return hits


def ignored(paths: list[Path]) -> set[str]:
    # ponytail: a local api/.env holds the token and is gitignored; CI still scans every tracked file
    relative = [str(path.relative_to(ROOT)) for path in paths]
    result = subprocess.run(["git", "check-ignore", "--stdin"], input="\n".join(relative), capture_output=True, text=True, cwd=ROOT)
    return set(result.stdout.splitlines())


def main() -> int:
    files = [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and path.name != "scan_secrets.py" and not any(part in SKIP for part in path.parts)
    ]
    skip = ignored(files)
    hits: list[str] = []
    for path in files:
        if str(path.relative_to(ROOT)) in skip:
            continue
        hits.extend(scan(path))
    if hits:
        print("secret-like token found:\n" + "\n".join(hits), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
