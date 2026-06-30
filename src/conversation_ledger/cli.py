from __future__ import annotations

import argparse
from pathlib import Path

from conversation_ledger.collector import CollectorService
from conversation_ledger.config import LedgerConfig
from conversation_ledger.context import build_day_context, build_thread_context, render_context_payload
from conversation_ledger.exporter import MarkdownExporter
from conversation_ledger.importer import ImportWatcher
from conversation_ledger.search import SearchRequest, render_search_payload, run_search
from conversation_ledger.shell import LedgerShellService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversation-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-storage", help="Create expected storage directories")
    subparsers.add_parser("run-collector", help="Run the local HTTP collector")
    subparsers.add_parser("run-shell", help="Run the local shell UI for browsing archived chats")

    scan_parser = subparsers.add_parser("scan-inbox", help="Import supported files from the inbox")
    scan_parser.add_argument("--project", required=True, help="Project identifier")

    import_parser = subparsers.add_parser("import-file", help="Import a single file")
    import_parser.add_argument("--project", required=True, help="Project identifier")
    import_parser.add_argument("--path", required=True, type=Path, help="Path to the source file")
    import_parser.add_argument("--thread", help="Optional thread identifier override")

    export_thread = subparsers.add_parser("export-thread", help="Export a thread to Markdown")
    export_thread.add_argument("--project", required=True)
    export_thread.add_argument("--platform", required=True)
    export_thread.add_argument("--thread", required=True)
    export_thread.add_argument("--output", type=Path)

    export_day = subparsers.add_parser("export-day", help="Export all project events for a day")
    export_day.add_argument("--project", required=True)
    export_day.add_argument("--date", required=True, help="ISO date in YYYY-MM-DD format")
    export_day.add_argument("--output", type=Path)

    search_parser = subparsers.add_parser("search", help="Search archived messages with explicit source grouping")
    search_parser.add_argument("--query", required=True, help="Word, phrase, or FTS expression to search for")
    search_parser.add_argument(
        "--scope",
        required=True,
        choices=("all", "project", "family", "project-family"),
        help="Choose the source group for the search",
    )
    search_parser.add_argument("--project", help="Project identifier for scope=project or scope=project-family")
    search_parser.add_argument(
        "--family",
        help="Platform family such as codex, chatgpt, claude_code, cursor, gemini, or deepseek",
    )
    search_parser.add_argument("--product", help="Concrete source product such as codex, chatgpt, cursor, lovable")
    search_parser.add_argument("--vendor", help="Runtime vendor such as openai, anthropic, google, deepseek")
    search_parser.add_argument(
        "--surface",
        help="Execution surface such as browser_web, cursor_plugin, cursor_native_picker, api_router",
    )
    search_parser.add_argument("--limit", type=int, default=5, help="Maximum number of hits to return")
    search_parser.add_argument("--window", type=int, default=1, help="Messages before/after the hit to include")

    thread_context = subparsers.add_parser("thread-context", help="Return grouped evidence for one thread")
    thread_context.add_argument("--project", required=True)
    thread_context.add_argument("--thread", required=True)
    thread_context.add_argument("--family")
    thread_context.add_argument("--product")
    thread_context.add_argument("--vendor")
    thread_context.add_argument("--surface")

    day_context = subparsers.add_parser("day-context", help="Return grouped evidence for one project day")
    day_context.add_argument("--project", required=True)
    day_context.add_argument("--date", required=True, help="ISO date in YYYY-MM-DD format")
    day_context.add_argument("--family")
    day_context.add_argument("--product")
    day_context.add_argument("--vendor")
    day_context.add_argument("--surface")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = LedgerConfig.from_env(repo_root=Path.cwd())

    if args.command == "init-storage":
        config.ensure_directories()
        print(config.data_root)
        return 0

    if args.command == "run-collector":
        CollectorService(config).run()
        return 0

    if args.command == "run-shell":
        LedgerShellService(config).run()
        return 0

    if args.command == "scan-inbox":
        results = ImportWatcher(config).scan_inbox(project_id=args.project)
        print(f"processed={len(results)} imported={sum(1 for item in results if item.imported)}")
        return 0

    if args.command == "import-file":
        result = ImportWatcher(config).import_file(path=args.path, project_id=args.project, thread_id=args.thread)
        print(f"imported={result.imported} duplicate={result.duplicate} event_id={result.event_id}")
        return 0

    if args.command == "export-thread":
        result = MarkdownExporter(config).export_thread(
            project_id=args.project,
            platform=args.platform,
            thread_id=args.thread,
            output_path=args.output,
        )
        print(result.output_path)
        return 0

    if args.command == "export-day":
        result = MarkdownExporter(config).export_project_day(
            project_id=args.project,
            iso_date=args.date,
            output_path=args.output,
        )
        print(result.output_path)
        return 0

    if args.command == "search":
        request = SearchRequest(
            query=args.query,
            scope=args.scope,
            project_id=args.project,
            platform_family=args.family,
            source_product=args.product,
            runtime_vendor=args.vendor,
            source_surface=args.surface,
            limit=args.limit,
            window=args.window,
        )
        payload = run_search(MarkdownExporter(config).index, request)
        print(render_search_payload(payload))
        return 0

    if args.command == "thread-context":
        payload = build_thread_context(
            MarkdownExporter(config).index,
            project_id=args.project,
            thread_id=args.thread,
            platform_family=args.family,
            source_product=args.product,
            runtime_vendor=args.vendor,
            source_surface=args.surface,
        )
        print(render_context_payload(payload))
        return 0

    if args.command == "day-context":
        payload = build_day_context(
            MarkdownExporter(config).index,
            project_id=args.project,
            iso_date=args.date,
            platform_family=args.family,
            source_product=args.product,
            runtime_vendor=args.vendor,
            source_surface=args.surface,
        )
        print(render_context_payload(payload))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
