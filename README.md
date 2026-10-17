# Codex Recall

Local-first, cross-platform search for your Codex CLI session history.

> Status: early development. The initial release is a read-only local indexer and search CLI. It does not upload session data.

## Requirements

- Python 3.11 or newer
- Codex CLI with local session files

## Quick start

```bash
git clone https://github.com/vwbugowner1976/codex-recall.git
cd codex-recall
python -m codex_recall --help
```

The project is being built for macOS, Windows, and Linux. See the usage guide as commands land.

## Privacy

Codex Recall reads session JSONL files locally and stores its search index in a local SQLite database. It never sends conversation content to a remote service. Do not commit your Codex history, generated database, or secrets.

## License

MIT
