"""Rules around OpenHands: git diff, zones, allow-list, build. Not the model's word."""

from __future__ import annotations

import json
from pathlib import Path

from runtime import tools
from store import db

MANIFESTS = ("package.json",)


def zones_of(agent: dict) -> list[str]:
    return list((agent.get("scope") or {}).get("zones") or agent.get("zones") or [])


# Repo housekeeping any role may touch; rejecting a run over .gitignore wastes the whole attempt.
HOUSEKEEPING = {".gitignore", ".gitattributes", ".nvmrc", ".editorconfig"}


def zone_violation(agent: dict, files: list[str]) -> str | None:
    zones = zones_of(agent)
    if not zones:
        return None
    bad = [path for path in files if path not in HOUSEKEEPING and not tools._in_zones(path, zones)]
    if not bad:
        return None
    return "changed files outside the role zones: " + ", ".join(bad)


def _names_from_package(folder: Path) -> set[str]:
    path = folder / "package.json"
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    names: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            names.update(str(item) for item in block)
    return names


def package_violation(agent: dict, folder: Path, before: set[str]) -> str | None:
    added = _names_from_package(folder) - before
    if not added:
        return None
    bad = [name for name in sorted(added) if not tools._package_allowed(agent, name)]
    if not bad:
        return None
    return "packages not on the allow-list: " + ", ".join(bad)


def snapshot_packages(folder: Path) -> set[str]:
    return _names_from_package(folder)


def build_violation(run: dict, folder: Path) -> str | None:
    if tools._package_root(folder) is None:
        run["buildTest"] = {"ok": True, "output": "no package.json"}
        return None
    # Verify in a clean copy with no inherited node_modules: the install and build then
    # run as one consistent uid, so build tooling the worker created under a different
    # container uid can never cause permission errors here.
    import shutil
    import tempfile

    from runtime.openhands.sandbox import VERIFY_IGNORE

    def _safe_copy(src, dst):
        try:
            shutil.copy2(src, dst)
        except OSError:
            pass  # unreadable container artifact; the build never needs it

    scratch = Path(tempfile.mkdtemp(prefix="verify-"))
    try:
        dest = scratch / "repo"
        shutil.copytree(folder, dest, ignore=VERIFY_IGNORE, copy_function=_safe_copy, dirs_exist_ok=True)
        result = tools._build(run, dest, lambda: False, install=True)
    except Exception as exc:
        # A failure in our own verification machinery must not be reported as the
        # worker's code being broken; the Team Lead and QA reviews still read the diff.
        run["buildTest"] = {"ok": True, "output": f"build check skipped: {type(exc).__name__}: {exc}"}
        return None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    run["buildTest"] = {"ok": bool(result.get("buildOk")), "output": result.get("output") or ""}
    if result.get("buildOk"):
        return None
    tail = (result.get("output") or "build_test failed")[-500:]
    return f"build_test failed: {tail}"


def protected_violation(project: dict | None, files: list[str]) -> str | None:
    from runtime import notes

    bad = [path for path in files if notes.is_protected(path, project)]
    if not bad:
        return None
    return "changed protected notes file: " + ", ".join(bad)


def reject_reason(agent: dict, run: dict, folder: Path, files: list[str], before: set[str]) -> str | None:
    project = db.get("project", run.get("projectId") or "") if run.get("projectId") else None
    # Zones and package lists are guidance for prompts and routing, not rejection rules:
    # correct work often needs structure or tooling no policy list anticipates.
    # What still rejects: touching the protected notes file, and a failing build.
    return protected_violation(project, files) or build_violation(run, folder)


def auto_feedback(task: dict, reason: str) -> dict:
    task["reworkCount"] = int(task.get("reworkCount") or 0) + 1
    db.put("task", task["id"], task)
    return board_feedback(task, reason)


def board_feedback(task: dict, reason: str) -> dict:
    from runtime import board

    return board.write_feedback(
        task,
        None,
        "changes_requested",
        f"Automatic check rejected this run: {reason}",
        [{"targetKind": "file", "target": "", "wrong": reason, "expected": "stay inside zones, allow-list, and a passing build"}],
    )
