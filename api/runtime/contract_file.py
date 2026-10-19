"""Write and read a role's optional contract file for later workers."""

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


def write_contract(folder: Path | None, summary: dict, rel: str = "api/CONTRACT.md") -> Path | None:
    if folder is None or not rel:
        return None
    target = folder / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(summary), encoding="utf-8")
    return target


def read_contract(folder: Path | None, rel: str = "api/CONTRACT.md") -> str:
    if folder is None or not rel:
        return ""
    target = folder / rel
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")[:8000]


def contracts_for_reader(folder: Path | None, agent: dict | None) -> str:
    if folder is None:
        return ""
    own = None
    try:
        from runtime import roles as rolelib

        own = rolelib.contract_file_of(agent)
    except Exception:
        own = None
    chunks = []
    seen: set[str] = set()
    from store import db

    for role in db.listing("role"):
        path = role.get("contractFile")
        if not path or path == own or path in seen:
            continue
        seen.add(path)
        body = read_contract(folder, path)
        if body:
            chunks.append(body)
    if not chunks:
        fallback = read_contract(folder)
        if fallback and fallback not in chunks:
            chunks.append(fallback)
    return "\n\n".join(chunks)
