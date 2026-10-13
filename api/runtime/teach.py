"""Create a skill, a stack, and an optional docs source, then attach them. Roll back if a later write fails."""

import os
import tempfile
from pathlib import Path

from gateway import openai_gateway
from store import db


def teach(agent_id: str, body: dict) -> dict | None:
    agent = db.get("agent", agent_id)
    if agent is None:
        return None
    name = (body.get("name") or "").strip()
    if not name or not (body.get("rules") or "").strip():
        raise ValueError("name and rules are required")
    timestamp = db.now()
    skill = {
        "id": db.nid("skill"),
        "name": name,
        "description": f"Load when writing {name}.",
        "body": body["rules"],
        "files": [],
        "version": 1,
        "versions": [{"version": 1, "createdAt": timestamp}],
        "origin": "teach",
        "createdAt": timestamp,
    }
    source = None
    if (body.get("docsUrl") or "").strip():
        source = {
            "id": db.nid("src"),
            "name": f"{name} docs",
            "kind": "url",
            "ref": body["docsUrl"].strip(),
            "refreshPolicy": "manual",
            "lastPulledAt": None,
            "pagesChanged": None,
            "versionTag": None,
        }
    stack = {
        "id": db.nid("stack"),
        "name": name,
        "version": body.get("version") or "",
        "skillIds": [skill["id"]],
        "dataSourceIds": [source["id"]] if source else [],
        "scaffoldTemplate": body.get("scaffold") or "",
        "packageAllowList": [item for item in body.get("packages") or [] if item],
        "enabledByDefault": True,
    }
    saved: list[tuple[str, str]] = []
    try:
        db.put("skill", skill["id"], skill)
        saved.append(("skill", skill["id"]))
        if source:
            db.put("datasource", source["id"], source)
            saved.append(("datasource", source["id"]))
        db.put("stack", stack["id"], stack)
        saved.append(("stack", stack["id"]))
        agent["skillIds"] = [*(agent.get("skillIds") or []), skill["id"]]
        agent["stackIds"] = [*(agent.get("stackIds") or []), stack["id"]]
        caps = dict(agent.get("capabilities") or {"stacks": [], "skills": [], "tags": []})
        caps["skills"] = list(agent["skillIds"])
        caps["stacks"] = list(agent["stackIds"])
        agent["capabilities"] = caps
        agent["updatedAt"] = db.now()
        db.put("agent", agent["id"], agent)
    except Exception:
        for kind, item_id in reversed(saved):
            db.delete(kind, item_id)
        raise
    result = {"agent": agent, "skill": skill, "stack": stack}
    if source:
        result["dataSource"] = source
    return result


def draft_rules(repo_url: str) -> str:
    if os.environ.get("GATEWAY_MOCK") == "1":
        return f"# {repo_url}\n\nUse the patterns in this repo."
    folder = Path(tempfile.mkdtemp(prefix="atelier-draft-"))
    import subprocess

    cloned = subprocess.run(["git", "clone", "--depth", "1", repo_url, str(folder)], capture_output=True, text=True)
    if cloned.returncode:
        raise RuntimeError(cloned.stderr[-500:] or "clone failed")
    chunks: list[str] = []
    for path in sorted(folder.rglob("*")):
        if ".git" in path.parts or not path.is_file() or path.stat().st_size > 40_000:
            continue
        if path.suffix.lower() not in {".md", ".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml"}:
            continue
        chunks.append(path.name + "\n" + path.read_text(errors="ignore")[:4000])
        if sum(len(item) for item in chunks) > 20_000:
            break
    turn = openai_gateway.complete(
        "gpt-4o",
        [{"role": "user", "content": "Write Markdown rules a frontend agent should follow in this repo. Read only.\n" + "\n\n".join(chunks)}],
        [],
        {},
    )
    return (turn.get("content") or "").strip() or f"# {repo_url}\n"
