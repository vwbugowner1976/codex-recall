import json
from pathlib import Path

from codex_recall.core import RecallIndex, _message_from_record, codex_home


def write_session(path: Path, messages: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{"type": "session_meta", "payload": {"id": "test-session"}}]
    for role, text in messages:
        records.append({
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
            },
        })
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_parse_codex_message_record():
    record = {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Found the WS2812 driver bug."}],
        },
    }
    assert _message_from_record(record) == ("assistant", "Found the WS2812 driver bug.", None)


def test_index_and_search(tmp_path: Path):
    home = tmp_path / ".codex"
    session = home / "sessions" / "2026" / "10" / "17" / "rollout-test.jsonl"
    write_session(session, [
        ("user", "Help me fix the WS2812 driver"),
        ("assistant", "The DMA transfer should not block interrupts"),
    ])
    db = tmp_path / "index.sqlite3"

    with RecallIndex(db) as index:
        result = index.index(home=home)
        assert result.indexed_files == 1
        assert result.indexed_messages == 2
        rows = index.search("WS2812")
        assert len(rows) == 1
        assert rows[0]["role"] == "user"
        assert "WS2812" in rows[0]["text"]
        assert index.stats()["sessions"] == 1

        result = index.index(home=home)
        assert result.skipped_files == 1
        assert result.indexed_files == 0


def test_reindex_updates_deleted_messages(tmp_path: Path):
    home = tmp_path / ".codex"
    session = home / "sessions" / "rollout-test.jsonl"
    write_session(session, [("assistant", "alpha searchable token")])
    db = tmp_path / "index.sqlite3"

    with RecallIndex(db) as index:
        index.index(home=home)
        write_session(session, [("assistant", "beta searchable token")])
        index.index(home=home, force=True)
        assert not index.search("alpha")
        assert len(index.search("beta")) == 1


def test_codex_home_override(monkeypatch, tmp_path: Path):
    custom = tmp_path / "custom-codex"
    monkeypatch.setenv("CODEX_HOME", str(custom))
    assert codex_home() == custom
