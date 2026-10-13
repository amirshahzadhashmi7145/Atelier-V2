from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_example_env_keeps_keys_short():
    for path in ROOT.rglob(".env.example"):
        for line in path.read_text().splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            name, value = line.split("=", 1)
            if name.endswith("_KEY") or name.endswith("_TOKEN"):
                assert len(value.strip().strip('"').strip("'")) <= 8, path
