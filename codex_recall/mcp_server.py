"""Optional MCP server exposing local history search to compatible clients."""
from __future__ import annotations

from pathlib import Path

from .core import RecallIndex, codex_home


def run_server(db_path: Path | None = None, home: Path | None = None) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError("Install MCP support with: python -m pip install -e '.[mcp]'") from exc

    server = FastMCP("codex-recall")
    resolved_home = home or codex_home()

    @server.tool()
    def search_codex_history(query: str, limit: int = 10, role: str = "") -> str:
        """Search previously indexed Codex conversations. Run index_codex_history first if needed."""
        with RecallIndex(db_path) as index:
            try:
                rows = index.search(query, limit=limit, role=role or None)
            except ValueError as exc:
                return str(exc)
        if not rows:
            return "No matching messages. Use index_codex_history to index local sessions first."
        return "\n\n".join(
            f"[{row['role']}] session={row['session_id']}"
            + (f" timestamp={row['timestamp']}" if row["timestamp"] else "")
            + f"\n{row['snippet']}\nsource={row['source_path']}"
            for row in rows
        )

    @server.tool()
    def index_codex_history(force: bool = False) -> str:
        """Index or refresh Codex session JSONL files on this computer. Files are read-only."""
        if not resolved_home.is_dir():
            return f"Codex home not found: {resolved_home}. Set CODEX_HOME or configure the server with the correct home."
        with RecallIndex(db_path) as index:
            result = index.index(home=resolved_home)
            stats = index.stats()
        return (
            f"Scanned {result.scanned_files}; indexed {result.indexed_files} files "
            f"and {result.indexed_messages} messages; unchanged {result.skipped_files}; "
            f"errors {result.errors}. Local database: {stats['database']}"
        )

    @server.tool()
    def codex_recall_stats() -> str:
        """Show the number of indexed sessions and messages."""
        with RecallIndex(db_path) as index:
            stats = index.stats()
        return f"Sessions: {stats['sessions']}\nMessages: {stats['messages']}\nDatabase: {stats['database']}"

    server.run(transport="stdio")
