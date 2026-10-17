"""Read-only importer for the Codex desktop app's local SQLite history.

This schema is an implementation detail of the desktop app and may change.
Only user and assistant text messages are imported; reasoning, tool output,
commands, diffs, and attachments are intentionally excluded.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import RecallIndex


@dataclass
class DesktopIndexResult:
    available: bool = False
    threads: int = 0
    messages: int = 0
    errors: int = 0


def _extract_text(item_type: str, raw: str | bytes) -> str | None:
    try:
        item: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(item, dict):
        return None

    if item_type == "userMessage":
        content = item.get("content")
        if not isinstance(content, list):
            return None
        parts = [
            part["text"]
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "\n".join(part.strip() for part in parts if part.strip())
    elif item_type == "agentMessage":
        value = item.get("text")
        text = value.strip() if isinstance(value, str) else ""
    else:
        return None

    return text if text else None


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def index_desktop_history(index: RecallIndex, home: Path) -> DesktopIndexResult:
    """Import desktop app text history into the existing local search index.

    The source database is opened read-only. The import is replaced atomically
    per source database so repeated runs do not duplicate messages.
    """
    db_path = (home / "thread_history_1.sqlite").expanduser()
    result = DesktopIndexResult()
    if not db_path.is_file():
        return result

    result.available = True
    try:
        uri = db_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as source:
            exists = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thread_items'"
            ).fetchone()
            if not exists:
                return result
            rows = source.execute("""
                SELECT thread_id, rollout_ordinal, created_at_ms, item_type, item_json
                FROM thread_items
                WHERE item_type IN ('userMessage', 'agentMessage')
                ORDER BY thread_id, rollout_ordinal
            """).fetchall()
    except (sqlite3.Error, OSError, ValueError):
        result.errors = 1
        return result

    db_stat = db_path.stat()
    source_prefix = f"codex-desktop:{db_path.resolve()}#"
    grouped: dict[str, list[tuple[str, str | None, str]]] = {}

    for thread_id, _ordinal, created_at_ms, item_type, raw in rows:
        if thread_id is None:
            continue
        text = _extract_text(item_type, raw)
        if not text:
            continue
        role = "user" if item_type == "userMessage" else "assistant"
        grouped.setdefault(str(thread_id), []).append(
            (role, _timestamp(created_at_ms), text)
        )

    indexed_at = datetime.now(timezone.utc).isoformat()
    try:
        with index.connection:
            old_sources = [
                row[0]
                for row in index.connection.execute(
                    "SELECT source_path FROM sessions"
                ).fetchall()
                if row[0].startswith(source_prefix)
            ]
            for source_path in old_sources:
                index.connection.execute(
                    "DELETE FROM messages WHERE source_path = ?", (source_path,)
                )
                index.connection.execute(
                    "DELETE FROM sessions WHERE source_path = ?", (source_path,)
                )

            for thread_id, messages in grouped.items():
                source_path = source_prefix + thread_id
                index.connection.execute(
                    """INSERT INTO sessions
                       (source_path, mtime_ns, size, session_id, indexed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (source_path, db_stat.st_mtime_ns, db_stat.st_size,
                     thread_id, indexed_at),
                )
                index.connection.executemany(
                    """INSERT INTO messages
                       (session_id, source_path, role, timestamp, text)
                       VALUES (?, ?, ?, ?, ?)""",
                    [
                        (thread_id, source_path, role, timestamp, text)
                        for role, timestamp, text in messages
                    ],
                )
                result.threads += 1
                result.messages += len(messages)
    except sqlite3.Error:
        result.errors = 1
        result.threads = 0
        result.messages = 0

    return result
