from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    event_count: int = 0
    imported_count: int = 0


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
            event_count=1,
            imported_count=int(append_result.accepted),
        )

    def import_codex_thread_snapshot(
        self,
        path: Path,
        project_id: str,
        thread_id: str | None = None,
    ) -> ImportResult:
        data = path.read_bytes()
        import_sha = sha256_bytes(data)
        snapshot = json.loads(data.decode("utf-8-sig"))
        snapshot_thread = snapshot.get("thread", {})
        resolved_thread_id = safe_thread_id(thread_id or str(snapshot_thread.get("id") or path.stem))

        if self.index.has_import(import_sha):
            return ImportResult(
                imported=False,
                duplicate=True,
                source_path=path,
                copied_to=None,
                event_id=None,
            )

        events = self._build_codex_thread_events(
            snapshot=snapshot,
            project_id=project_id,
            thread_id=resolved_thread_id,
        )

        copy_name = f"{import_sha[:12]}_{path.name}"
        copied_to = self.config.imports_original_root / copy_name
        copied_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied_to)

        imported_count = 0
        for event in events:
            append_result = self.store.append_event(event)
            imported_count += int(append_result.accepted)

        self.index.record_import(
            import_sha256=import_sha,
            source_name=path.name,
            source_path=path,
            copied_to=copied_to,
            thread_id=resolved_thread_id,
            project_id=project_id,
        )

        normalized_payload = {
            "import_type": "codex_thread_snapshot",
            "import_sha256": import_sha,
            "source_path": str(path),
            "copied_to": str(copied_to),
            "thread_id": resolved_thread_id,
            "project_id": project_id,
            "event_count": len(events),
            "imported_count": imported_count,
            "codex_thread_id": snapshot_thread.get("id"),
            "thread_title": snapshot_thread.get("title"),
        }
        normalized_path = self.config.normalized_root / f"{import_sha}.json"
        normalized_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return ImportResult(
            imported=imported_count > 0,
            duplicate=False,
            source_path=path,
            copied_to=copied_to,
            event_id=events[0].event_id if events else None,
            event_count=len(events),
            imported_count=imported_count,
        )

    def _normalize_content(self, path: Path, data: bytes) -> str:
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(data.decode("utf-8"))
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return data.decode("utf-8", errors="replace")
        return data.decode("utf-8", errors="replace")

    def _build_codex_thread_events(
        self,
        *,
        snapshot: dict[str, Any],
        project_id: str,
        thread_id: str,
    ) -> list[ConversationEvent]:
        page = snapshot.get("page", {})
        turns = list(snapshot.get("turns", []))
        if page.get("order") == "newest_first":
            turns.reverse()

        events: list[ConversationEvent] = []
        for turn in turns:
            turn_id = str(turn.get("id") or "turn")
            turn_status = str(turn.get("status") or "completed")
            items = list(turn.get("items", []))
            for index, item in enumerate(items):
                event = self._build_codex_item_event(
                    project_id=project_id,
                    thread_id=thread_id,
                    turn=turn,
                    turn_id=turn_id,
                    turn_status=turn_status,
                    item=item,
                    item_index=index,
                )
                if event is not None:
                    events.append(event)

        if not events:
            raise ValueError("No importable Codex messages found in snapshot")
        return events

    def _build_codex_item_event(
        self,
        *,
        project_id: str,
        thread_id: str,
        turn: dict[str, Any],
        turn_id: str,
        turn_status: str,
        item: dict[str, Any],
        item_index: int,
    ) -> ConversationEvent | None:
        item_type = str(item.get("type") or "")
        role = self._codex_role_for(item_type)
        if role is None:
            return None

        content_markdown = self._codex_item_text(item)
        if not content_markdown.strip():
            return None

        item_id = str(item.get("id") or f"{turn_id}-item-{item_index}")
        event_type = "message_revision" if role == "assistant" and turn_status != "completed" else "message_final"
        timestamp_observed = self._codex_item_timestamp(turn=turn, role=role, item_index=item_index)
        event_seed = f"codex:{project_id}:{thread_id}:{turn_id}:{item_id}:{event_type}:{content_markdown}"

        attachment_refs = [
            {
                "source": "codex_thread_snapshot",
                "turn_id": turn_id,
                "turn_status": turn_status,
                "item_id": item_id,
                "item_type": item_type,
                "phase": item.get("phase"),
            }
        ]

        return ConversationEvent(
            event_id=sha256_text(event_seed),
            project_id=project_id,
            platform="codex",
            thread_id=thread_id,
            message_id=item_id,
            timestamp_observed=timestamp_observed,
            role=role,
            event_type=event_type,
            content_markdown=content_markdown,
            capture_adapter="codex-thread-snapshot@0.1.0",
            source_product="codex",
            runtime_vendor="openai",
            source_surface="codex_app_thread",
            attachment_refs=attachment_refs,
            source_url=f"codex-thread://{thread_id}/turn/{turn_id}/item/{item_id}",
        )

    def _codex_role_for(self, item_type: str) -> str | None:
        if item_type == "userMessage":
            return "user"
        if item_type == "agentMessage":
            return "assistant"
        return None

    def _codex_item_text(self, item: dict[str, Any]) -> str:
        item_type = str(item.get("type") or "")
        if item_type == "agentMessage":
            return str(item.get("text") or "")
        parts = self._collect_text_fragments(item.get("content", []))
        return "\n".join(part for part in parts if part.strip()).strip()

    def _collect_text_fragments(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            fragments: list[str] = []
            for item in value:
                fragments.extend(self._collect_text_fragments(item))
            return fragments
        if isinstance(value, dict):
            fragments: list[str] = []
            text = value.get("text")
            if isinstance(text, str):
                fragments.append(text)
            for key in ("content", "children", "parts", "items"):
                if key in value:
                    fragments.extend(self._collect_text_fragments(value[key]))
            return fragments
        return []

    def _codex_item_timestamp(self, *, turn: dict[str, Any], role: str, item_index: int) -> str:
        epoch_seconds = turn.get("startedAt")
        if role == "assistant" and turn.get("completedAt") is not None:
            epoch_seconds = turn.get("completedAt")
        if epoch_seconds is None:
            return utc_now_iso()
        base_time = datetime.fromtimestamp(float(epoch_seconds), UTC)
        return (
            base_time.replace(microsecond=min(item_index, 999999))
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
