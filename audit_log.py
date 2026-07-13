"""
audit_log.py — Command-usage tracking for Rythmify.

Records every slash-command invocation to audit_log.json with:
  - timestamp (ISO-8601)
  - user_id / user_name
  - guild_id / guild_name
  - command name
  - options (query, mode, etc.)

Rotates at AUDIT_LOG_MAX_SIZE bytes (default 10 MB).
"""

import json
import os
import sys
import datetime
from typing import Optional

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "audit_log.json")
_MAX_SIZE = int(os.getenv("AUDIT_LOG_MAX_SIZE", str(10 * 1024 * 1024)))  # 10 MB
_MAX_QUEUE = int(os.getenv("AUDIT_LOG_MAX_QUEUE", "1000"))  # in-memory cap before forced flush/drop
_QUEUE: list[dict] = []
_FLUSH_INTERVAL = 5  # seconds between flushes to disk


def _load_existing() -> list[dict]:
    """Return existing entries from disk, or []."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-5000:]  # cap on load
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _write(data: list[dict]) -> None:
    """Atomically write the full log to disk (rotates if too large)."""
    if sys.getsizeof(data) > _MAX_SIZE:
        # Keep only the newest half
        data = data[-(len(data) // 2):]
    tmp = AUDIT_LOG_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, AUDIT_LOG_PATH)
    except OSError as e:
        print(f"[audit_log] Write error: {e}", file=sys.stderr)


def record_command(
    user_id: int,
    user_name: str,
    guild_id: Optional[int],
    guild_name: Optional[str],
    command: str,
    options: Optional[dict] = None,
) -> None:
    """Add a command-usage record to the in-memory queue."""
    global _QUEUE
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "user_name": user_name,
        "guild_id": guild_id,
        "guild_name": guild_name,
        "command": command,
        "options": options or {},
    }
    _QUEUE.append(entry)
    # Prevent unbounded memory growth if flush is delayed or fails
    if len(_QUEUE) > _MAX_QUEUE:
        dropped = _QUEUE[:len(_QUEUE) - _MAX_QUEUE]
        _QUEUE = _QUEUE[-_MAX_QUEUE:]
        print(f"[audit_log] Dropped {len(dropped)} entries due to in-memory queue overflow")


def flush() -> int:
    """Flush queued entries to disk. Returns number flushed."""
    global _QUEUE
    if not _QUEUE:
        return 0
    entries = _QUEUE
    _QUEUE = []
    existing = _load_existing()
    existing.extend(entries)
    _write(existing)
    return len(entries)


def get_stats() -> dict:
    """Return simple statistics (for the /audit command or debugging)."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return {"total_commands": 0, "unique_users": 0}
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {"total_commands": 0, "unique_users": 0}
        users = set(e["user_id"] for e in data)
        return {
            "total_commands": len(data),
            "unique_users": len(users),
        }
    except (json.JSONDecodeError, OSError):
        return {"total_commands": 0, "unique_users": 0}


def get_recent(limit: int = 20) -> list[dict]:
    """Return the most recent entries (latest first)."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data[-limit:][::-1]
    except (json.JSONDecodeError, OSError):
        return []
