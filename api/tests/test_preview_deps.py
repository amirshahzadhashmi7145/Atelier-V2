"""Tests that the live preview reinstalls node_modules when a task added a
dependency to package.json without installing it — the stale-dependency case
that broke the dev server with a missing @stripe/* import."""

from __future__ import annotations

import json
from pathlib import Path

from runtime import tools


def _write_pkg(folder: Path, deps: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(json.dumps({"name": "demo", "dependencies": deps, "scripts": {"dev": "vite"}}))


def test_deps_satisfied_true_when_all_present(tmp_path: Path):
    _write_pkg(tmp_path, {"react": "^18", "@stripe/react-stripe-js": "^2"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)
    (tmp_path / "node_modules" / "@stripe" / "react-stripe-js").mkdir(parents=True)
    assert tools._deps_satisfied(tmp_path) is True


def test_deps_satisfied_false_when_a_declared_dep_is_missing(tmp_path: Path):
    # package.json lists the stripe package but node_modules has only react.
    _write_pkg(tmp_path, {"react": "^18", "@stripe/react-stripe-js": "^2"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)
    assert tools._deps_satisfied(tmp_path) is False


def test_deps_satisfied_false_when_node_modules_absent(tmp_path: Path):
    _write_pkg(tmp_path, {"react": "^18"})
    assert tools._deps_satisfied(tmp_path) is False


def test_deps_satisfied_true_without_package_json(tmp_path: Path):
    assert tools._deps_satisfied(tmp_path) is True


def test_preview_reinstalls_when_dependency_missing(tmp_path: Path, monkeypatch):
    _write_pkg(tmp_path, {"react": "^18", "@stripe/react-stripe-js": "^2"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)  # stale: stripe not installed

    captured: dict[str, str] = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            self.pid = 4321

    monkeypatch.setattr(tools.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(tools, "stop_preview", lambda project_id: None)

    tools._preview({"id": "run_x", "projectId": "prj_x"}, tmp_path)
    assert "npm install" in captured["command"]
    assert "npm run dev" in captured["command"]


def _write_buildable_pkg(folder: Path, deps: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": deps, "scripts": {"build": "vite build", "test": "vitest run"}})
    )


def test_build_test_reconciles_declared_but_uninstalled_dep(tmp_path: Path, monkeypatch):
    # A worker declared @stripe/* in package.json but node_modules is stale. build_test
    # (install=True) must install the declared deps itself so a supervisor that cannot run
    # package_install can still produce a passing build instead of asking the user.
    _write_buildable_pkg(tmp_path, {"react": "^18", "@stripe/react-stripe-js": "^2"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)  # stripe missing

    commands: list[str] = []

    def fake_run_command(folder, command, should_stop, timeout=120):
        commands.append(command)
        if "npm run" in command:
            return (0, "ok")
        # pretend the install materialised the missing package
        (Path(folder) / "node_modules" / "@stripe" / "react-stripe-js").mkdir(parents=True, exist_ok=True)
        return (0, "added 1 package")

    monkeypatch.setattr(tools.sandbox, "run_command", fake_run_command)
    result = tools._build({"id": "run_b"}, tmp_path, lambda: False, install=True)

    assert result["buildOk"] is True
    assert any("npm ci" in c or "npm install" in c for c in commands)  # it reconciled deps
    assert any("npm run build" in c for c in commands)


def test_build_test_skips_install_when_all_deps_present(tmp_path: Path, monkeypatch):
    _write_buildable_pkg(tmp_path, {"react": "^18"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)

    commands: list[str] = []
    monkeypatch.setattr(
        tools.sandbox, "run_command", lambda folder, command, should_stop, timeout=120: commands.append(command) or (0, "ok")
    )
    result = tools._build({"id": "run_c"}, tmp_path, lambda: False, install=True)

    assert result["buildOk"] is True
    assert not any("npm ci" in c or "npm install" in c for c in commands)  # nothing to reconcile


def test_preview_skips_install_when_deps_satisfied(tmp_path: Path, monkeypatch):
    _write_pkg(tmp_path, {"react": "^18"})
    (tmp_path / "node_modules" / "react").mkdir(parents=True)

    captured: dict[str, str] = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            self.pid = 4322

    monkeypatch.setattr(tools.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(tools, "stop_preview", lambda project_id: None)

    tools._preview({"id": "run_y", "projectId": "prj_y"}, tmp_path)
    assert "npm install" not in captured["command"]
    assert "npm run dev" in captured["command"]
