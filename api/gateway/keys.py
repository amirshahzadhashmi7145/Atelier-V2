"""Encrypted provider API keys. Never log the raw key; never return it after save."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_HINT_SHORT = "••••"
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{8,}|atk_[A-Za-z0-9_-]{8,})")
_KNOWN: dict[str, str] = {}


def secrets_dir() -> Path:
    root = Path(os.environ.get("PROJECTS_DIR") or Path.home() / ".atelier-projects")
    path = root / ".secrets" / "providers"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, stat.S_IRWXU)
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


def _fernet() -> Fernet:
    folder = secrets_dir().parent
    path = folder / "master.key"
    if path.is_file():
        secret = path.read_bytes().strip()
    else:
        secret = Fernet.generate_key()
        path.write_bytes(secret)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return Fernet(secret)


def mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) < 12:
        return _HINT_SHORT
    return f"{key[:3]}…{key[-4:]}"


def redact(text: str | None) -> str:
    if not text:
        return ""
    out = text
    for value in list(_KNOWN.values()):
        if value and value in out:
            out = out.replace(value, mask(value) or _HINT_SHORT)
    return _SECRET_RE.sub(lambda match: mask(match.group(0)) or _HINT_SHORT, out)


def path_for(provider_id: str) -> Path:
    return secrets_dir() / f"{provider_id}.enc"


def save(provider_id: str, api_key: str) -> str:
    token = api_key.strip()
    if not token:
        raise ValueError("apiKey is required")
    blob = _fernet().encrypt(token.encode("utf-8"))
    dest = path_for(provider_id)
    dest.write_bytes(blob)
    try:
        os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    _KNOWN[provider_id] = token
    return mask(token) or _HINT_SHORT


def load(provider_id: str) -> str | None:
    dest = path_for(provider_id)
    if not dest.is_file():
        _KNOWN.pop(provider_id, None)
        return None
    if provider_id in _KNOWN:
        return _KNOWN[provider_id]
    try:
        token = _fernet().decrypt(dest.read_bytes()).decode("utf-8")
    except (InvalidToken, ValueError, OSError):
        return None
    _KNOWN[provider_id] = token
    return token


def has(provider_id: str) -> bool:
    return bool(load(provider_id))


def hint(provider_id: str) -> str | None:
    return mask(load(provider_id))


def delete(provider_id: str) -> None:
    _KNOWN.pop(provider_id, None)
    dest = path_for(provider_id)
    if dest.is_file():
        dest.unlink()


def env_fallback(env_var: str | None) -> str | None:
    if not env_var:
        return None
    value = os.environ.get(env_var, "").strip()
    return value or None
