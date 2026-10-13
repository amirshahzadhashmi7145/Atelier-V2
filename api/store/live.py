"""In-memory deltas. Subscribers see them immediately; the database does not."""

import queue
import threading

_lock = threading.Lock()
_subs: dict[str, list[queue.Queue]] = {}
_buf: dict[str, list[dict]] = {}
_parts: dict[tuple[str, str], dict[int, str]] = {}
_seq = 0


def reset() -> None:
    global _seq
    with _lock:
        _subs.clear()
        _buf.clear()
        _parts.clear()
        _seq = 0


def delta(run_id: str, call_id: str, index: int, text: str) -> dict:
    global _seq
    with _lock:
        _parts.setdefault((run_id, call_id), {})[index] = text
        _seq += 1
        seq = 1_000_000 + _seq
    event = {
        "id": f"delta_{call_id}_{index}",
        "runId": run_id,
        "seq": seq,
        "type": "MODEL_DELTA",
        "actor": {"kind": "agent", "role": "agent"},
        "payload": {"modelCallId": call_id, "callId": call_id, "index": index, "text": text},
        "occurredAt": "",
    }
    from store import db

    event["occurredAt"] = db.now()
    _publish(run_id, event, remember=True)
    return event


def ordered_text(run_id: str, call_id: str) -> str:
    with _lock:
        parts = _parts.get((run_id, call_id), {})
        return "".join(parts[index] for index in sorted(parts))


def finish(run_id: str, call_id: str) -> str:
    with _lock:
        parts = _parts.pop((run_id, call_id), {})
        text = "".join(parts[index] for index in sorted(parts))
        _buf[run_id] = [item for item in _buf.get(run_id, []) if (item.get("payload") or {}).get("modelCallId") != call_id]
    return text


def subscribe(run_id: str) -> queue.Queue:
    inbox: queue.Queue = queue.Queue()
    with _lock:
        _subs.setdefault(run_id, []).append(inbox)
        pending = list(_buf.get(run_id, []))
    for event in pending:
        inbox.put(event)
    return inbox


def unsubscribe(run_id: str, inbox: queue.Queue) -> None:
    with _lock:
        rows = _subs.get(run_id, [])
        if inbox in rows:
            rows.remove(inbox)


def _publish(run_id: str, event: dict, remember: bool) -> None:
    with _lock:
        if remember:
            _buf.setdefault(run_id, []).append(event)
        queues = list(_subs.get(run_id, []))
    for inbox in queues:
        inbox.put(event)
