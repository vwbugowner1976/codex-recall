# Codex Recall

**Local-first, cross-platform search for Codex conversation history.**

Codex Recall indexes Codex CLI JSONL transcripts and, when available, the Codex desktop app's local SQLite history. Search both from the terminal with SQLite FTS5. The index and imported conversation text stay on your computer.

> **Status:** early development (0.1.0). The CLI index/search workflow is implemented; the optional MCP server is experimental.

## Requirements

- Python 3.11+
- Codex CLI JSONL history and/or the Codex desktop app with local history
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
python -m pip install --upgrade pip setuptools
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

- **index** scans sessions/ and archived_sessions/ JSONL files under your Codex home and imports `thread_history_1.sqlite` when the desktop app database is present. Desktop history is refreshed on each run; JSONL files that have not changed are skipped.
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

- Source JSONL files and the desktop app SQLite database are opened read-only; the indexer never edits or deletes the originals.
- Desktop import includes user and assistant text messages only. Reasoning, command output, file diffs, and tool-call payloads are excluded by default.
- The desktop app's SQLite schema is an implementation detail and may change in future app versions; this importer may need maintenance.
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
