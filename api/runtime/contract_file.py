"""Write and read api/CONTRACT.md between backend and frontend runs."""

from __future__ import annotations

from pathlib import Path


def render(summary: dict) -> str:
    lines = ["# API contract", ""]
    description = (summary.get("description") or "").strip()
    if description:
        lines.extend([description, ""])
    endpoints = summary.get("endpoints") or []
    if not endpoints:
        lines.append("No endpoints listed in the completion summary.")
        return "\n".join(lines) + "\n"
    lines.extend(["| Method | Path | Request | Response |", "| --- | --- | --- | --- |"])
    for item in endpoints:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {method} | {path} | {request} | {response} |".format(
                method=item.get("method") or "",
                path=item.get("path") or "",
                request=item.get("request") or "",
                response=item.get("response") or "",
            )
        )
    return "\n".join(lines) + "\n"


def write_contract(folder: Path | None, summary: dict) -> Path | None:
    if folder is None:
        return None
    target = folder / "api" / "CONTRACT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(summary), encoding="utf-8")
    return target


def read_contract(folder: Path | None) -> str:
    if folder is None:
        return ""
    target = folder / "api" / "CONTRACT.md"
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")[:8000]
