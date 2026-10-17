# Codex Recall

**Local-first, cross-platform search for Codex CLI session history.**

Codex Recall indexes the JSONL session transcripts saved by Codex CLI and makes them searchable from the terminal. It is designed for macOS, Windows, and Linux, and keeps both the index and session content on your computer.

> **Status:** early development (0.1.0). The CLI index/search workflow is implemented; the optional MCP server is experimental.

## Requirements

- Python 3.11+
- Codex CLI with local session history
- SQLite with FTS5 support (included in most standard Python builds)

## Quick start

### macOS / Linux

~~~bash
git clone https://github.com/vwbugowner1976/codex-recall.git
cd codex-recall
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
codex-recall index
codex-recall search "WS2812"
~~~

### Windows (PowerShell)

~~~powershell
git clone https://github.com/vwbugowner1976/codex-recall.git
cd codex-recall
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
codex-recall index
codex-recall search "WS2812"
~~~

If PowerShell blocks activation, skip activation and run the Python executable inside the .venv folder directly.

## Commands

~~~text
codex-recall index [--home PATH] [--force]
codex-recall search QUERY [-n 10] [--role user|assistant|system|developer]
codex-recall stats
codex-recall mcp [--home PATH]
~~~

- **index** scans sessions/ and archived_sessions/ under your Codex home. Unchanged files are skipped; deleted files are removed from the index.
- **search** uses SQLite FTS5 syntax. For multiple terms, try the command with the query "WS2812 driver". FTS5 supports quoted phrases and operators.
- **stats** shows index counts and the database path.
- **--force** reindexes all files.
- **--home PATH** selects a custom Codex home. The CODEX_HOME environment variable is respected automatically.

## Data locations

By default Codex Recall reads from:

- macOS / Linux: ~/.codex/sessions/
- Windows: %USERPROFILE%\.codex\sessions\

If CODEX_HOME is set, that directory takes precedence. The index is stored separately at ~/.codex-recall/index.sqlite3 (Windows: %USERPROFILE%\.codex-recall\index.sqlite3). Set CODEX_RECALL_DB or pass --db PATH to change it.

## Optional MCP integration

Install the optional dependency:

~~~bash
python -m pip install -e ".[mcp]"
~~~

Then configure your MCP-compatible Codex client to launch codex-recall mcp with the same Python environment. The server provides:

- search_codex_history — search indexed messages
- index_codex_history — index or refresh local sessions
- codex_recall_stats — show index counts

Exact Codex MCP configuration can vary by CLI version and installation method; see the Codex documentation for the supported config format. The server uses stdio and does not expose a network listener.

## Privacy and safety

- Session files are read-only; the indexer never edits or deletes the originals.
- Search index files are stored outside this repository by default.
- No cloud service or telemetry is used by this tool.
- Do not commit session JSONL files, the SQLite database, or secrets.
- Search results may contain sensitive text from your own conversations. Treat terminal output accordingly.

## Development

~~~bash
python -m pip install -e ".[dev]"
python -m pytest
~~~

## License

MIT
