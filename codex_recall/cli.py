"""Command-line interface for Codex Recall."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import RecallIndex, codex_home, default_db_path
from .desktop import index_desktop_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-recall",
        description="Search your local Codex CLI session history. Data stays on this computer.",
    )
    parser.add_argument("--db", type=Path, default=None, help="SQLite index path (default: ~/.codex-recall/index.sqlite3)")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="Index Codex CLI JSONL and desktop app history")
    index.add_argument("--home", type=Path, default=None, help="Codex home (default: CODEX_HOME or ~/.codex)")
    index.add_argument("--force", action="store_true", help="Reindex every session file")

    search = sub.add_parser("search", help="Search indexed conversation text")
    search.add_argument("query", help='FTS5 query, e.g. "WS2812 driver"')
    search.add_argument("-n", "--limit", type=int, default=10, help="Maximum results (1-100)")
    search.add_argument("--role", choices=("user", "assistant", "system", "developer"), help="Filter by message role")

    sub.add_parser("stats", help="Show local index statistics")
    mcp = sub.add_parser("mcp", help="Run the optional MCP server over stdio")
    mcp.add_argument("--home", type=Path, default=None, help="Codex home used for indexing")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = args.db or default_db_path()

    if args.command == "mcp":
        try:
            from .mcp_server import run_server
        except ImportError:
            print("MCP support is optional. Install it with: python -m pip install -e '.[mcp]'", file=sys.stderr)
            return 2
        run_server(db_path=db_path, home=args.home)
        return 0

    try:
        with RecallIndex(db_path) as index:
            if args.command == "index":
                home = args.home or codex_home()
                if not home.is_dir():
                    print(f"Codex home not found: {home}", file=sys.stderr)
                    print("Set CODEX_HOME or pass --home PATH.", file=sys.stderr)
                    return 1
                result = index.index(home=home, force=args.force)
                desktop = index_desktop_history(index, home)
                print(f"Codex home: {home}")
                print(f"Database:   {db_path}")
                print(f"Scanned JSONL: {result.scanned_files}")
                print(f"Indexed JSONL: {result.indexed_files} files / {result.indexed_messages} messages")
                print(f"Unchanged JSONL: {result.skipped_files}")
                if desktop.available:
                    print(f"Desktop history: {desktop.threads} threads / {desktop.messages} messages")
                print(f"Errors:     {result.errors + desktop.errors}")
                return 1 if result.errors or desktop.errors else 0

            if args.command == "stats":
                stats = index.stats()
                print(f"Database: {stats['database']}")
                print(f"Sessions: {stats['sessions']}")
                print(f"Messages: {stats['messages']}")
                return 0

            if args.command == "search":
                try:
                    rows = index.search(args.query, limit=args.limit, role=args.role)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                if not rows:
                    print("No matches. Run codex-recall index first, or try different search terms.")
                    return 0
                for i, row in enumerate(rows, start=1):
                    when = f" | {row['timestamp']}" if row["timestamp"] else ""
                    print(f"\n{i}. [{row['role']}] {row['session_id']}{when}")
                    print(f"   File: {row['source_path']}")
                    print(f"   {row['snippet']}")
                return 0
    except (OSError, RuntimeError) as exc:
        print(f"codex-recall: {exc}", file=sys.stderr)
        return 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
