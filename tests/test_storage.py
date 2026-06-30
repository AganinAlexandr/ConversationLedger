from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.storage import AppendOnlyRawStore


class AppendOnlyStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = LedgerConfig(
            commons_root=root / "commons",
            data_root=root / "commons" / "data" / "conversation_ledger",
            knowledge_root=root / "commons" / "knowledge" / "conversation_ledger",
            output_root=root / "output" / "conversation-ledger",
            collector_token="test-token",
        )
        self.config.ensure_directories()
        self.index = LedgerIndex(self.config.db_path)
        self.store = AppendOnlyRawStore(self.config.raw_root, self.index)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_append_only_deduplicates_but_keeps_revision(self) -> None:
        event = ConversationEvent(
            event_id="evt-1",
            project_id="sorting-center",
            platform="codex",
            thread_id="thread-1",
            message_id="msg-1",
            timestamp_observed="2026-06-30T10:00:00Z",
            role="assistant",
            event_type="message_final",
            content_markdown="first answer",
            capture_adapter="test-adapter@0.1.0",
        )
        duplicate = ConversationEvent.from_dict(event.to_dict())
        revision = ConversationEvent(
            event_id="evt-2",
            project_id="sorting-center",
            platform="codex",
            thread_id="thread-1",
            message_id="msg-1",
            parent_message_id="msg-1",
            timestamp_observed="2026-06-30T10:01:00Z",
            role="assistant",
            event_type="message_revision",
            content_markdown="first answer, edited",
            capture_adapter="test-adapter@0.1.0",
        )

        first_result = self.store.append_event(event)
        duplicate_result = self.store.append_event(duplicate)

        restarted_store = AppendOnlyRawStore(self.config.raw_root, LedgerIndex(self.config.db_path))
        revision_result = restarted_store.append_event(revision)

        self.assertTrue(first_result.accepted)
        self.assertTrue(duplicate_result.duplicate)
        self.assertTrue(revision_result.accepted)

        lines = first_result.raw_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        payloads = [json.loads(line) for line in lines]
        self.assertEqual(payloads[0]["event_id"], "evt-1")
        self.assertEqual(payloads[1]["event_id"], "evt-2")


if __name__ == "__main__":
    unittest.main()

