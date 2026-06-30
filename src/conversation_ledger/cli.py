from __future__ import annotations

import argparse
from pathlib import Path

from conversation_ledger.collector import CollectorService
from conversation_ledger.config import LedgerConfig
from conversation_ledger.exporter import MarkdownExporter
from conversation_ledger.importer import ImportWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversation-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-storage", help="Create expected storage directories")
    subparsers.add_parser("run-collector", help="Run the local HTTP collector")

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

    parser.error(f"Unsupported command: {args.command}")
    return 2

