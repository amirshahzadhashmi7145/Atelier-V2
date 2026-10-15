import json
import subprocess
from pathlib import Path

import pytest

from runtime.scaffold import write_vite_react_ts


@pytest.mark.slow
def test_vite_react_ts_starter_builds(tmp_path):
    folder = tmp_path / "vite-app"
    write_vite_react_ts(folder)
    package = json.loads((folder / "package.json").read_text())
    assert "dev" in package["scripts"]
    assert "build" in package["scripts"]
    assert "test" in package["scripts"]
    subprocess.run(["npm", "install"], cwd=folder, check=True, timeout=180)
    subprocess.run(["npm", "run", "build"], cwd=folder, check=True, timeout=180)
