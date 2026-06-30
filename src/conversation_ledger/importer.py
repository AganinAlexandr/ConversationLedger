from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.storage import AppendOnlyRawStore
from conversation_ledger.utils import safe_thread_id, sha256_bytes, sha256_text, utc_now_iso

SUPPORTED_IMPORT_SUFFIXES = {".txt", ".md", ".html", ".json"}


@dataclass(slots=True)
class ImportResult:
    imported: bool
    duplicate: bool
    source_path: Path
    copied_to: Path | None
    event_id: str | None


class ImportWatcher:
    def __init__(self, config: LedgerConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.index = LedgerIndex(config.db_path)
        self.store = AppendOnlyRawStore(config.raw_root, self.index)

    def scan_inbox(self, project_id: str) -> list[ImportResult]:
        results: list[ImportResult] = []
        for path in sorted(self.config.inbox_path.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMPORT_SUFFIXES:
                results.append(self.import_file(path=path, project_id=project_id))
        return results

    def import_file(self, path: Path, project_id: str, thread_id: str | None = None) -> ImportResult:
        data = path.read_bytes()
        import_sha = sha256_bytes(data)
        resolved_thread_id = safe_thread_id(thread_id or path.stem)

        if self.index.has_import(import_sha):
            return ImportResult(
                imported=False,
                duplicate=True,
                source_path=path,
                copied_to=None,
                event_id=None,
            )

        copy_name = f"{import_sha[:12]}_{path.name}"
        copied_to = self.config.imports_original_root / copy_name
        copied_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied_to)

        content_markdown = self._normalize_content(path, data)
        timestamp = utc_now_iso()
        message_id = import_sha[:16]
        event = ConversationEvent(
            event_id=sha256_text(f"{project_id}:{resolved_thread_id}:{import_sha}:import_record"),
            project_id=project_id,
            platform="import",
            thread_id=resolved_thread_id,
            message_id=message_id,
            timestamp_observed=timestamp,
            role="unknown",
            event_type="import_record",
            content_markdown=content_markdown,
            capture_adapter="manual-import@0.1.0",
            source_url=str(path),
        )
        append_result = self.store.append_event(event)
        self.index.record_import(
            import_sha256=import_sha,
            source_name=path.name,
            source_path=path,
            copied_to=copied_to,
            thread_id=resolved_thread_id,
            project_id=project_id,
        )

        normalized_payload = {
            "import_sha256": import_sha,
            "source_path": str(path),
            "copied_to": str(copied_to),
            "event_id": event.event_id,
            "thread_id": resolved_thread_id,
            "project_id": project_id,
        }
        normalized_path = self.config.normalized_root / f"{import_sha}.json"
        normalized_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return ImportResult(
            imported=append_result.accepted,
            duplicate=append_result.duplicate,
            source_path=path,
            copied_to=copied_to,
            event_id=event.event_id,
        )

    def _normalize_content(self, path: Path, data: bytes) -> str:
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(data.decode("utf-8"))
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return data.decode("utf-8", errors="replace")
        return data.decode("utf-8", errors="replace")

