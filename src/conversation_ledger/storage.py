from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.utils import ensure_parent, stable_json_dumps


@dataclass(slots=True)
class AppendResult:
    accepted: bool
    duplicate: bool
    raw_path: Path


class AppendOnlyRawStore:
    def __init__(self, raw_root: Path, index: LedgerIndex) -> None:
        self.raw_root = raw_root
        self.index = index
        self.raw_root.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: ConversationEvent) -> AppendResult:
        raw_path = self._raw_path_for(event)
        if self.index.has_event(event):
            return AppendResult(accepted=False, duplicate=True, raw_path=raw_path)

        ensure_parent(raw_path)
        with raw_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(stable_json_dumps(event.to_dict()))
            handle.write("\n")

        self.index.record_event(event, raw_path)
        return AppendResult(accepted=True, duplicate=False, raw_path=raw_path)

    def load_raw_events(self, raw_path: Path) -> list[ConversationEvent]:
        events: list[ConversationEvent] = []
        if not raw_path.exists():
            return events
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(ConversationEvent.from_dict(json.loads(line)))
        return events

    def _raw_path_for(self, event: ConversationEvent) -> Path:
        month = datetime.fromisoformat(event.timestamp_observed.replace("Z", "+00:00")).strftime("%Y-%m")
        return self.raw_root / event.platform / month / f"{event.thread_id}.jsonl"

