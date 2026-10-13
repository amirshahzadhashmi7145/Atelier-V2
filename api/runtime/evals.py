import shutil
import tempfile
import time
from pathlib import Path

from runtime import loop
from store import db


def run_version(agent: dict, version: dict, model_name: str | None = None) -> dict:
    results = []
    for item in agent.get("evals") or []:
        results.append(_one(agent, version, item, model_name))
    version["evalResults"] = results
    db.put("version", version["id"], version)
    return version


def compare_models(agent: dict, version: dict, models: list[str]) -> dict:
    previous = list(version.get("evalResults") or [])
    rows = []
    for name in models:
        run_version(agent, version, name)
        results = version.get("evalResults") or []
        passed = [item for item in results if item["status"] == "pass"]
        count = len(results) or 1
        rows.append(
            {
                "model": name,
                "passRate": len(passed) / count,
                "avgCostUsd": sum(item.get("costUsd") or 0 for item in results) / count,
                "avgDurationMs": sum(item.get("durationMs") or 0 for item in results) / count,
            }
        )
    version["evalResults"] = previous
    db.put("version", version["id"], version)
    return {"rows": rows}


def _one(agent: dict, version: dict, item: dict, model_name: str | None) -> dict:
    started = time.time()
    model = dict(agent.get("model") or {"provider": "openai", "name": "gpt-5", "config": {}})
    if model_name:
        model["name"] = model_name
    criteria = item.get("criteria") or []
    task = f"{item.get('task') or ''}\nPass rule: {item.get('passRule') or ''}\nCriteria:\n" + "\n".join(criteria)
    run_id = db.nid("run")
    folder = Path(tempfile.mkdtemp(prefix="atelier-eval-", dir=db.projects_dir()))
    run = {
        "id": run_id,
        "agentId": agent["id"],
        "promptVersionId": version["id"],
        "model": model,
        "workspace": {"kind": "scaffold", "template": "local"},
        "task": task,
        "criteria": criteria,
        "attachmentIds": [],
        "status": "queued",
        "iterations": 0,
        "tokensIn": 0,
        "tokensOut": 0,
        "costUsd": 0,
        "startedAt": db.now(),
    }
    try:
        db.put("workspace", run_id, {"folder": str(folder)})
        db.put("run", run_id, run)
        loop.drive(run_id)
        finished = db.get("run", run_id) or run
        status, evidence = judge(finished, item)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return {
        "evalId": item["id"],
        "status": status,
        "evidence": evidence,
        "costUsd": (db.get("run", run_id) or {}).get("costUsd") or 0,
        "durationMs": int((time.time() - started) * 1000),
        "runId": run_id,
    }


def judge(run: dict, item: dict) -> tuple[str, str]:
    if run.get("status") != "completed":
        return "fail", run.get("terminalCause") or "the run did not finish"
    summary = run.get("summary") or {}
    found = {}
    for entry in summary.get("criteria") or []:
        if isinstance(entry, dict) and entry.get("evidence"):
            found[entry.get("text")] = entry["evidence"]
    missing = [text for text in item.get("criteria") or [] if not found.get(text)]
    if missing:
        return "fail", "missing evidence for " + ", ".join(missing)
    rule = item.get("passRule") or ""
    artifacts = [entry for entry in db.listing("artifact") if entry.get("runId") == run["id"]]
    if _wants_build(rule):
        logs = [entry for entry in artifacts if entry.get("kind") == "log" and entry.get("ok")]
        if not logs:
            return "fail", "build or tests failed"
    if _wants_shots(rule):
        shots = [entry for entry in artifacts if entry.get("kind") == "screenshot"]
        if {entry.get("viewport") for entry in shots} < {"mobile", "tablet", "desktop"}:
            return "fail", "missing a screenshot"
        if any(entry.get("consoleErrors") for entry in shots):
            return "fail", "console errors"
    return "pass", summary.get("description") or "passed"


def _wants_build(rule: str) -> bool:
    return rule in ("build_and_tests", "build_tests_and_screenshots") or "build" in rule.lower()


def _wants_shots(rule: str) -> bool:
    return rule == "build_tests_and_screenshots" or "screenshot" in rule.lower()
