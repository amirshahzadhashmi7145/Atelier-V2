import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "web" / "src" / "mocks" / "seed.generated.json"


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(String)


_engine = None
LOCK = threading.RLock()


def engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'api' / 'atelier.db'}")
        _engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(_engine)
        seed()
    return _engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def session() -> Session:
    return Session(engine())


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get(kind: str, item_id: str):
    with LOCK, session() as db:
        row = db.get(Document, (kind, item_id))
        return json.loads(row.data) if row else None


def put(kind: str, item_id: str, data: dict) -> dict:
    payload = json.dumps(data)
    with LOCK, session() as db:
        row = db.get(Document, (kind, item_id))
        if row is None:
            db.add(Document(kind=kind, id=item_id, data=payload))
        else:
            row.data = payload
        db.commit()
    return data


def delete(kind: str, item_id: str) -> None:
    with LOCK, session() as db:
        row = db.get(Document, (kind, item_id))
        if row is not None:
            db.delete(row)
            db.commit()


def listing(kind: str) -> list[dict]:
    with LOCK, session() as db:
        rows = db.scalars(select(Document).where(Document.kind == kind)).all()
        return [json.loads(row.data) for row in rows]


def nid(prefix: str) -> str:
    with LOCK:
        meta = get("meta", "counter") or {"n": 100}
        meta["n"] += 1
        put("meta", "counter", meta)
        return f"{prefix}_{meta['n']}"


def projects_dir() -> Path:
    raw = os.environ.get("PROJECTS_DIR") or str(Path.home() / "AgentStudio" / "projects")
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


BUILTIN_TOOLS = [
    ("shell", "builtin", "write", "Run a command in the workspace.", {"command": {"type": "string"}}, ["command"], "builtin"),
    ("files", "builtin", "write", "Read and write files inside the agent zones.", {"op": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}}, ["path"], "builtin"),
    ("package_install", "builtin", "write", "Install a package that is on an enabled allow-list.", {"name": {"type": "string"}}, ["name"], "builtin"),
    ("build_test", "builtin", "write", "Run the project build and tests.", {}, [], "builtin"),
    ("headless_browser", "builtin", "external", "Open a page and capture a screenshot.", {"url": {"type": "string"}}, [], "builtin"),
    ("preview_deploy", "builtin", "external", "Publish the workspace preview.", {}, [], "builtin"),
    ("search_data", "builtin", "read", "Search the data sources attached to this agent.", {"query": {"type": "string"}}, ["query"], "builtin"),
    ("load_skill", "control", "read", "Load a skill body into the context.", {"name": {"type": "string"}}, ["name"], "control"),
    ("complete", "control", "write", "Finish the run with a summary.", {"summary": {"type": "object"}}, ["summary"], "control"),
    ("raise_clarification", "control", "read", "Ask the user a question and wait.", {"question": {"type": "string"}}, ["question"], "control"),
    ("escalate", "control", "external", "Hand the run to a person.", {"reason": {"type": "string"}}, ["reason"], "control"),
    ("create_task", "control", "write", "Create a follow-up task.", {"text": {"type": "string"}}, ["text"], "control"),
    ("record_review", "control", "write", "Record a review of a task.", {"taskId": {"type": "string"}, "verdict": {"type": "string"}, "notes": {"type": "string"}}, ["taskId", "verdict", "notes"], "control"),
]


def tool_record(item) -> dict:
    tool_id, kind, permission, description, properties, required, source = item
    return {
        "id": tool_id,
        "kind": kind,
        "name": tool_id,
        "description": description,
        "schema": {"type": "object", "additionalProperties": False, "properties": properties, "required": required},
        "permission": permission,
        "config": {},
        "source": source,
        "enabled": True,
    }


def seed() -> None:
    if get("meta", "seeded"):
        return
    for item in BUILTIN_TOOLS:
        record = tool_record(item)
        put("tool", record["id"], record)
    put(
        "provider",
        "openai",
        {
            "id": "openai",
            "name": "OpenAI",
            "keyRef": "env:OPENAI_API_KEY" if os.environ.get("OPENAI_API_KEY") else None,
            "connected": False,
            "modelsCachedAt": None,
        },
    )
    put(
        "settings",
        "runs",
        {"maxSpendPerRunUsd": 5, "maxIterations": 60, "maxMinutes": 45, "loopDetection": True},
    )
    put("meta", "seeded", {"ok": True})


def library() -> dict:
    return json.loads(SEED_PATH.read_text())["library"]


def append_event(run_id: str, event_type: str, payload: dict | None = None, cost: dict | None = None, actor: str = "agent") -> dict:
    with LOCK:
        existing = [item for item in listing("event") if item["runId"] == run_id]
        seq = len(existing) + 1
        event = {
            "id": nid("evt"),
            "runId": run_id,
            "seq": seq,
            "type": event_type,
            "actor": {"kind": "system" if event_type == "STATE_CHANGED" else actor, "role": "agent"},
            "payload": payload or {},
            "occurredAt": now(),
        }
        if cost:
            event["cost"] = cost
        put("event", event["id"], event)
        return event


def events_for(run_id: str, after: int = 0) -> list[dict]:
    rows = [item for item in listing("event") if item["runId"] == run_id and item["seq"] > after]
    return sorted(rows, key=lambda item: item["seq"])
