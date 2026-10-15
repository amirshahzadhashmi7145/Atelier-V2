import json
from pathlib import Path

import pytest

from runtime.tool_results import format_tool_result
from runtime.tools import dispatch
from store import db


@pytest.fixture
def run_and_folder(tmp_path):
    run_id = "run_tool_test"
    folder = tmp_path / "ws"
    folder.mkdir()
    (folder / "package.json").write_text('{"name":"x","scripts":{"build":"node -e \\"process.exit(0)\\"","test":"node -e \\"process.exit(0)\\""}}')
    run = {"id": run_id, "agentId": "agt_x", "folder": str(folder), "task": "test"}
    db.put("workspace", run_id, {"folder": str(folder)})
    db.put("run", run_id, run)
    db.put("agent", "agt_x", {"id": "agt_x", "toolIds": ["files", "build_test", "load_skill"], "stackIds": [], "skillIds": []})
    db.put("skill", "sk1", {"id": "sk1", "name": "Demo", "description": "d", "body": "Skill body text"})
    yield run, folder


def test_files_read_nonempty():
    text = format_tool_result("files", {"op": "read", "path": "x"}, {"output": "file bytes"})
    assert text.strip()


def test_files_list_nonempty():
    text = format_tool_result("files", {"op": "list", "path": "."}, {"output": "a\nb"})
    assert text.strip()


def test_load_skill_and_already_loaded(run_and_folder):
    run, folder = run_and_folder
    first = dispatch(run, "load_skill", {"name": "Demo"}, lambda: False)
    t1 = format_tool_result("load_skill", {"name": "Demo"}, first)
    assert "Skill body" in t1
    second = dispatch(run, "load_skill", {"name": "Demo"}, lambda: False)
    t2 = format_tool_result("load_skill", {"name": "Demo"}, second)
    assert t2.startswith("already loaded:")


def test_build_test_tail(run_and_folder):
    run, folder = run_and_folder
    result = dispatch(run, "build_test", {}, lambda: False)
    text = format_tool_result("build_test", {}, result)
    assert text.strip()


def test_files_read_via_dispatch(run_and_folder):
    run, folder = run_and_folder
    path = Path(folder) / "hello.txt"
    path.write_text("hi")
    result = dispatch(run, "files", {"op": "read", "path": "hello.txt"}, lambda: False)
    assert format_tool_result("files", {"op": "read", "path": "hello.txt"}, result).strip()
