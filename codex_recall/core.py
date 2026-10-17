"""Read-only Codex JSONL ingestion and local SQLite full-text search."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def codex_home() -> Path:
    """Return CODEX_HOME if set, otherwise the standard per-user directory."""
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


def default_db_path() -> Path:
    override = os.environ.get("CODEX_RECALL_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex-recall" / "index.sqlite3"


def session_roots(home: Path | None = None) -> list[Path]:
    home = home or codex_home()
    candidates = [home / "sessions", home / "archived_sessions"]
    return [p for p in candidates if p.is_dir()]


def iter_session_files(roots: list[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        for path in root.rglob("*.jsonl"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved not in seen and path.is_file():
                seen.add(resolved)
                yield path


def _walk_text(value: Any) -> Iterator[str]:
    """Extract text from Codex message content blocks without indexing metadata."""
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and value.get("type") in {
            "input_text", "output_text", "text", "input_text_delta",
            "output_text_delta", "refusal",
        }:
            if text_value.strip():
                yield text_value
        for key, child in value.items():
            if key in {"content", "message"}:
                yield from _walk_text(child)
            elif isinstance(child, (dict, list)) and key not in {
                "arguments", "metadata", "annotations", "summary",
            }:
                yield from _walk_text(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_text(child)


def _message_from_record(record: Any) -> tuple[str, str, str | None] | None:
    if not isinstance(record, dict):
        return None
    kind = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = record

    role = payload.get("role")
    payload_type = payload.get("type")
    if role not in {"user", "assistant", "system", "developer"}:
        # Some event records store the role in a nested message object.
        nested = payload.get("message")
        if isinstance(nested, dict):
            role = nested.get("role")
            if role not in {"user", "assistant", "system", "developer"}:
                return None
            payload = nested
        else:
            # Ignore tool calls and non-conversation events.
            if kind not in {"message", "user_message", "agent_message"}:
                return None
            return None

    if payload_type not in {None, "message"} and kind == "response_item":
        return None

    parts = list(_walk_text(payload.get("content", [])))
    if not parts:
        # Handle simpler JSONL variants with a direct text field.
        direct = payload.get("text")
        if isinstance(direct, str) and direct.strip():
            parts = [direct]
    text = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not text:
        return None

    timestamp = record.get("timestamp") or payload.get("timestamp")
    if isinstance(timestamp, (int, float)):
        timestamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    elif not isinstance(timestamp, str):
        timestamp = None
    return str(role), text, timestamp


@dataclass
class IndexResult:
    scanned_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    indexed_messages: int = 0
    errors: int = 0


class RecallIndex:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path = self.db_path.expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "RecallIndex":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _initialize(self) -> None:
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS sessions (
                source_path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                session_id TEXT,
                indexed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                role TEXT NOT NULL,
                timestamp TEXT,
                text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source_path);
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                text,
                content='messages',
                content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
            END;
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
                INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
            END;
        """)
        self.connection.commit()

    def index(self, home: Path | None = None, force: bool = False) -> IndexResult:
        result = IndexResult()
        roots = session_roots(home)
        known = {
            row["source_path"]: (row["mtime_ns"], row["size"])
            for row in self.connection.execute("SELECT source_path, mtime_ns, size FROM sessions")
        }
        current_paths: set[str] = set()

        for path in iter_session_files(roots):
            result.scanned_files += 1
            source = str(path.resolve())
            current_paths.add(source)
            try:
                stat = path.stat()
                fingerprint = (stat.st_mtime_ns, stat.st_size)
                if not force and known.get(source) == fingerprint:
                    result.skipped_files += 1
                    continue

                session_id = path.stem
                messages: list[tuple[str, str, str | None]] = []
                with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(record, dict) and record.get("type") == "session_meta":
                            meta = record.get("payload", {})
                            if isinstance(meta, dict) and meta.get("id"):
                                session_id = str(meta["id"])
                        parsed = _message_from_record(record)
                        if parsed:
                            messages.append(parsed)

                with self.connection:
                    self.connection.execute("DELETE FROM messages WHERE source_path = ?", (source,))
                    self.connection.execute("DELETE FROM sessions WHERE source_path = ?", (source,))
                    self.connection.executemany(
                        """INSERT INTO messages(session_id, source_path, role, timestamp, text)
                           VALUES (?, ?, ?, ?, ?)""",
                        [(session_id, source, role, timestamp, text) for role, text, timestamp in messages],
                    )
                    self.connection.execute(
                        """INSERT INTO sessions(source_path, mtime_ns, size, session_id, indexed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (source, stat.st_mtime_ns, stat.st_size, session_id,
                         datetime.now(timezone.utc).isoformat()),
                    )
                result.indexed_files += 1
                result.indexed_messages += len(messages)
            except (OSError, sqlite3.Error):
                result.errors += 1

        # Remove index records for session files that have been deleted or moved.
        stale = set(known) - current_paths
        for source in stale:
            with self.connection:
                self.connection.execute("DELETE FROM messages WHERE source_path = ?", (source,))
                self.connection.execute("DELETE FROM sessions WHERE source_path = ?", (source,))
        return result

    def search(self, query: str, limit: int = 10, role: str | None = None) -> list[sqlite3.Row]:
        if not query.strip():
            return []
        limit = max(1, min(int(limit), 100))
        sql = """
            SELECT m.session_id, m.source_path, m.role, m.timestamp, m.text,
                   snippet(messages_fts, 0, '[', ']', ' … ', 18) AS snippet,
                   bm25(messages_fts) AS rank
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            WHERE messages_fts MATCH ?
        """
        params: list[Any] = [query]
        if role:
            sql += " AND m.role = ?"
            params.append(role)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            return list(self.connection.execute(sql, params).fetchall())
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Invalid search query: {exc}") from exc

    def stats(self) -> dict[str, int | str]:
        sessions = self.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        messages = self.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return {
            "database": str(self.db_path),
            "sessions": int(sessions),
            "messages": int(messages),
        }
