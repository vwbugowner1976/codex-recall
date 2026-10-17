import json
import sqlite3
from pathlib import Path

from codex_recall.core import RecallIndex
from codex_recall.desktop import index_desktop_history


def make_desktop_db(home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    db = home / "thread_history_1.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("""
            CREATE TABLE thread_items (
                thread_id TEXT,
                turn_id TEXT,
                item_id TEXT,
                rollout_ordinal INTEGER,
                created_at_ms INTEGER,
                item_json TEXT,
                item_type TEXT,
                updated_at_ordinal INTEGER,
                started_at_ms INTEGER,
                completed_at_ms INTEGER
            )
        """)
        items = [
            ("thread-a", "turn-1", "item-1", 1, 1792195200000,
             {"type": "userMessage", "id": "item-1",
              "content": [{"type": "text", "text":
                  "Find the WS2812 driver. Attached file: C:\\Users\\G9\\.codex-remote-attachments\\abc\\secretfilename.txt"}]},
             "userMessage"),
            ("thread-a", "turn-1", "item-2", 2, 1792195201000,
             {"type": "agentMessage", "id": "item-2",
              "text": "The DMA transfer needs a safe buffer."},
             "agentMessage"),
            ("thread-a", "turn-1", "item-3", 3, 1792195202000,
             {"type": "reasoning", "id": "item-3", "summary": ["private reasoning"]},
             "reasoning"),
        ]
        con.executemany("""
            INSERT INTO thread_items
            (thread_id, turn_id, item_id, rollout_ordinal, created_at_ms,
             item_json, item_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (thread_id, turn_id, item_id, ordinal, created_at,
             json.dumps(obj), item_type)
            for thread_id, turn_id, item_id, ordinal, created_at, obj, item_type in items
        ])
    return db


def test_import_desktop_history_and_skip_reasoning(tmp_path: Path):
    home = tmp_path / ".codex"
    make_desktop_db(home)

    with RecallIndex(tmp_path / "index.sqlite3") as index:
        result = index_desktop_history(index, home)
        assert result.available
        assert result.threads == 1
        assert result.messages == 2
        assert len(index.search("WS2812")) == 1
        assert len(index.search("buffer")) == 1
        assert not index.search("private reasoning")
        assert not index.search("secretfilename")
        assert index.stats()["sessions"] == 1
        assert index.stats()["messages"] == 2


def test_desktop_import_is_idempotent_and_survives_jsonl_index(tmp_path: Path):
    home = tmp_path / ".codex"
    make_desktop_db(home)
    (home / "sessions").mkdir()

    with RecallIndex(tmp_path / "index.sqlite3") as index:
        first = index_desktop_history(index, home)
        second = index_desktop_history(index, home)
        index.index(home=home)

        assert first.messages == second.messages == 2
        assert index.stats()["sessions"] == 1
        assert index.stats()["messages"] == 2
        assert len(index.search("WS2812")) == 1


def test_missing_desktop_database_is_not_an_error(tmp_path: Path):
    with RecallIndex(tmp_path / "index.sqlite3") as index:
        result = index_desktop_history(index, tmp_path / ".codex")
        assert not result.available
        assert result.errors == 0
