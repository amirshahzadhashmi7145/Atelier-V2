import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import String, create_engine, func, select
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
_generation = 0
LOCK = threading.RLock()


def engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'api' / 'atelier.db'}")
        _engine = create_engine(url, connect_args={"check_same_thread": False})
        if url.startswith("sqlite"):
            with _engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                conn.commit()
        Base.metadata.create_all(_engine)
        if url.startswith("sqlite"):
            with _engine.connect() as conn:
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS idx_event_run "
                    "ON documents(json_extract(data,'$.runId')) WHERE kind='event'"
                )
                conn.commit()
        seed()
        sync_builtin_tools()
        sync_providers()
        sync_stored_model_ids()
        sync_stack_allow_lists()
        from runtime.roles import sync_roles

        sync_roles()
    return _engine


def reset_engine() -> None:
    global _engine, _generation
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _generation += 1
    try:
        from runtime.supervisor.graph import reset_compiled

        reset_compiled()
    except Exception:
        pass


def generation() -> int:
    return _generation


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
    (
        "files",
        "builtin",
        "write",
        "Read, list, edit, append, or write files. Prefer edit for existing files; write only for new files. "
        "Do not re-read the same path; after one read, write or edit source files under src/.",
        {
            "op": {"type": "string", "enum": ["read", "list", "write", "edit", "append"]},
            "path": {"type": "string"},
            "content": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path"],
        "builtin",
    ),
    ("package_install", "builtin", "write", "Install a package that is on an enabled allow-list.", {"name": {"type": "string"}}, ["name"], "builtin"),
    ("build_test", "builtin", "write", "Run the project build and tests.", {}, [], "builtin"),
    ("headless_browser", "builtin", "external", "Open a page and capture a screenshot.", {"url": {"type": "string"}}, [], "builtin"),
    ("preview_deploy", "builtin", "external", "Publish the workspace preview.", {}, [], "builtin"),
    ("search_data", "builtin", "read", "Search the data sources attached to this agent.", {"query": {"type": "string"}}, ["query"], "builtin"),
    ("load_skill", "control", "read", "Load a skill body into the context.", {"name": {"type": "string"}}, ["name"], "control"),
    ("complete", "control", "write", "Finish the run with a summary.", {"summary": {"type": "object"}}, ["summary"], "control"),
    ("raise_clarification", "control", "read", "Ask the user a question and wait.", {"question": {"type": "string"}}, ["question"], "control"),
    ("escalate", "control", "external", "Hand the run to a person.", {"reason": {"type": "string"}}, ["reason"], "control"),
    (
        "create_task",
        "control",
        "write",
        "Create a child task for a project member. Set assignToAgentId, acceptanceCriteria, and order. Do not start the work yourself.",
        {
            "text": {"type": "string"},
            "assignToAgentId": {"type": "string"},
            "acceptanceCriteria": {"type": "array", "items": {"type": "string"}},
            "order": {"type": "integer"},
        },
        ["text"],
        "control",
    ),
    (
        "record_review",
        "control",
        "write",
        "Record a review of a child task. verdict is approve or changes_requested.",
        {
            "taskId": {"type": "string"},
            "verdict": {"type": "string"},
            "notes": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "targetKind": {"type": "string"},
                        "target": {"type": "string"},
                        "wrong": {"type": "string"},
                        "expected": {"type": "string"},
                    },
                },
            },
        },
        ["verdict", "notes"],
        "control",
    ),
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
    sync_providers()
    put(
        "settings",
        "runs",
        {
            "maxSpendPerRunUsd": 5,
            "maxSpendPerDayUsd": 0,
            "maxIterations": 60,
            "maxMinutes": 45,
            "loopDetection": True,
            "recordModelRequests": False,
            "approvePlansBeforeRunning": False,
            "maxLessonsPerRole": 20,
            "maxSpendPerReviewUsd": 1,
        },
    )
    put("meta", "seeded", {"ok": True})
    sync_builtin_tools()


SEED_PROVIDERS = (
    {"id": "openai", "name": "OpenAI", "litellmPrefix": "openai/", "envVar": "OPENAI_API_KEY"},
    {"id": "gemini", "name": "Google Gemini", "litellmPrefix": "gemini/", "envVar": "GEMINI_API_KEY"},
)


def sync_providers() -> None:
    known = {spec["id"]: spec for spec in SEED_PROVIDERS}
    for spec in SEED_PROVIDERS:
        row = get("provider", spec["id"]) or {
            "id": spec["id"],
            "connected": False,
            "modelsCachedAt": None,
        }
        row["name"] = row.get("name") or spec["name"]
        row["litellmPrefix"] = spec["litellmPrefix"]
        row["envVar"] = row.get("envVar") or spec["envVar"]
        put("provider", spec["id"], row)
    for row in listing("provider"):
        if row["id"] in known or row.get("litellmPrefix"):
            continue
        row["litellmPrefix"] = f"{row['id']}/"
        put("provider", row["id"], row)


def sync_stored_model_ids() -> None:
    from app.models_catalog import model_id, normalize_spec

    for agent in listing("agent"):
        changed = False
        for key in ("model", "backupModel"):
            spec = normalize_spec(agent.get(key) if isinstance(agent.get(key), dict) else None)
            if spec is not None and spec != agent.get(key):
                agent[key] = spec
                changed = True
        if changed:
            put("agent", agent["id"], agent)
    with LOCK, session() as sess:
        cache_rows = [(row.id, json.loads(row.data)) for row in sess.scalars(select(Document).where(Document.kind == "model-cache")).all()]
    for cache_id, cached in cache_rows:
        ids = cached.get("ids") or []
        cleaned = [model_id(str(name)) for name in ids]
        if cleaned != ids:
            cached["ids"] = cleaned
            put("model-cache", cache_id, cached)


def sync_builtin_tools() -> None:
    for item in BUILTIN_TOOLS:
        record = tool_record(item)
        put("tool", record["id"], record)


def sync_stack_allow_lists() -> None:
    """Add new library allow-list packages onto stacks that were imported earlier."""
    try:
        templates = json.loads(SEED_PATH.read_text())["library"]["stacks"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return
    for template in templates:
        stack_id = template.get("id")
        existing = get("stack", stack_id) if stack_id else None
        if not existing:
            continue
        allow = list(existing.get("packageAllowList") or [])
        extra = [name for name in (template.get("packageAllowList") or []) if name not in allow]
        if extra:
            existing["packageAllowList"] = allow + extra
            put("stack", stack_id, existing)


def library() -> dict:
    return json.loads(SEED_PATH.read_text())["library"]


def _run_events(run_id: str) -> list[dict]:
    """Events for one run, filtered in SQL so the whole event table is never deserialised."""
    if engine().dialect.name == "sqlite":
        with LOCK, session() as db:
            rows = db.scalars(
                select(Document).where(Document.kind == "event", func.json_extract(Document.data, "$.runId") == run_id)
            ).all()
            return [json.loads(row.data) for row in rows]
    return [item for item in listing("event") if item["runId"] == run_id]


def append_event(run_id: str, event_type: str, payload: dict | None = None, cost: dict | None = None, actor: str = "agent") -> dict:
    with LOCK:
        # Per-run sequence counter so appends are O(1) instead of rescanning the
        # run's events on every event (which was O(n^2) across a run). Initialized
        # lazily from existing events so a run already in flight keeps counting up.
        meta = get("event-seq", run_id)
        if meta is None:
            last = max((item["seq"] for item in _run_events(run_id)), default=0)
            meta = {"n": last}
        seq = int(meta["n"]) + 1
        meta["n"] = seq
        put("event-seq", run_id, meta)
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
    rows = [item for item in _run_events(run_id) if item["seq"] > after]
    return sorted(rows, key=lambda item: item["seq"])
