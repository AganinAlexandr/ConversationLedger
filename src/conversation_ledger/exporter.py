from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.index import LedgerIndex, StoredEvent
from conversation_ledger.utils import ensure_parent, sha256_text


@dataclass(slots=True)
class ExportResult:
    output_path: Path
    sha256: str
    event_count: int


class MarkdownExporter:
    def __init__(self, config: LedgerConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.index = LedgerIndex(config.db_path)

    def export_thread(
        self,
        project_id: str,
        platform: str,
        thread_id: str,
        output_path: Path | None = None,
    ) -> ExportResult:
        events = self.index.fetch_thread_events(project_id=project_id, platform=platform, thread_id=thread_id)
        if output_path is None:
            output_path = self.config.exports_root / project_id / f"{thread_id}.md"
        document = self._render_document(
            title=f"Conversation Thread: {thread_id}",
            metadata_lines=[
                f"- project_id: {project_id}",
                f"- platform: {platform}",
                f"- thread_id: {thread_id}",
            ],
            events=events,
        )
        return self._write_export(output_path, document, len(events))

    def export_project_day(
        self,
        project_id: str,
        iso_date: str,
        output_path: Path | None = None,
    ) -> ExportResult:
        events = self.index.fetch_project_day_events(project_id=project_id, iso_date=iso_date)
        if output_path is None:
            output_path = self.config.exports_root / project_id / f"{iso_date}.md"
        document = self._render_document(
            title=f"Project Day: {project_id} / {iso_date}",
            metadata_lines=[
                f"- project_id: {project_id}",
                f"- date: {iso_date}",
            ],
            events=events,
        )
        return self._write_export(output_path, document, len(events))

    def _render_document(
        self,
        title: str,
        metadata_lines: list[str],
        events: list[StoredEvent],
    ) -> str:
        sections = [f"# {title}", "", *metadata_lines, "", "## Events", ""]
        for stored in events:
            event = stored.event
            sections.extend(
                [
                    f"### {event.timestamp_observed} [{event.role}] {event.event_type}",
                    f"- platform: {event.platform}",
                    f"- message_id: {event.message_id}",
                    f"- event_id: {event.event_id}",
                    f"- raw_path: {stored.raw_path}",
                    "",
                    event.content_markdown,
                    "",
                ]
            )
        return "\n".join(sections).rstrip() + "\n"

    def _write_export(self, output_path: Path, document: str, event_count: int) -> ExportResult:
        ensure_parent(output_path)
        output_path.write_text(document, encoding="utf-8")
        digest = sha256_text(document)
        output_path.with_suffix(output_path.suffix + ".sha256").write_text(
            f"{digest}  {output_path.name}\n",
            encoding="utf-8",
        )
        return ExportResult(output_path=output_path, sha256=digest, event_count=event_count)

