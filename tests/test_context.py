from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.context import build_day_context, build_thread_context
from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.storage import AppendOnlyRawStore


class ContextTests(unittest.TestCase):
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
        self._seed_events()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_thread_context_returns_full_grouped_thread(self) -> None:
        payload = build_thread_context(
            self.index,
            project_id="alpha",
            thread_id="thread-a",
        )
        self.assertEqual(payload["result_type"], "thread_context")
        self.assertEqual(payload["thread_count"], 1)
        group = payload["threads"][0]
        self.assertEqual(group["message_count"], 3)
        self.assertEqual(group["source_product"], "codex")

    def test_thread_context_can_filter_by_surface(self) -> None:
        payload = build_thread_context(
            self.index,
            project_id="gamma",
            thread_id="thread-d",
            platform_family="claude_code",
            source_surface="cursor_claude_code_plugin",
        )
        self.assertEqual(payload["thread_count"], 1)
        self.assertEqual(payload["threads"][0]["runtime_vendor"], "anthropic")

    def test_day_context_groups_multiple_threads(self) -> None:
        payload = build_day_context(
            self.index,
            project_id="beta",
            iso_date="2026-06-30",
        )
        self.assertEqual(payload["result_type"], "day_context")
        self.assertEqual(payload["thread_count"], 2)
        thread_ids = {group["thread_id"] for group in payload["threads"]}
        self.assertEqual(thread_ids, {"thread-b", "thread-c"})

    def test_day_context_can_filter_to_one_product(self) -> None:
        payload = build_day_context(
            self.index,
            project_id="beta",
            iso_date="2026-06-30",
            source_product="chatgpt",
        )
        self.assertEqual(payload["thread_count"], 1)
        self.assertEqual(payload["threads"][0]["thread_id"], "thread-b")

    def _seed_events(self) -> None:
        events = [
            self._event("evt-001", "alpha", "codex", "thread-a", "msg-001", "2026-06-30T10:00:00Z", "a1", "codex", "openai", "browser_web"),
            self._event("evt-002", "alpha", "codex", "thread-a", "msg-002", "2026-06-30T10:01:00Z", "a2", "codex", "openai", "browser_web"),
            self._event("evt-003", "alpha", "codex", "thread-a", "msg-003", "2026-06-30T10:02:00Z", "a3", "codex", "openai", "browser_web"),
            self._event("evt-004", "beta", "chatgpt", "thread-b", "msg-004", "2026-06-30T11:00:00Z", "b1", "chatgpt", "openai", "browser_web"),
            self._event("evt-005", "beta", "codex", "thread-c", "msg-005", "2026-06-30T12:00:00Z", "c1", "codex", "openai", "browser_web"),
            self._event("evt-006", "gamma", "claude_code", "thread-d", "msg-006", "2026-06-30T13:00:00Z", "d1", "claude_code", "anthropic", "cursor_claude_code_plugin"),
        ]
        for event in events:
            self.store.append_event(event)

    def _event(
        self,
        event_id: str,
        project_id: str,
        platform: str,
        thread_id: str,
        message_id: str,
        timestamp: str,
        content: str,
        source_product: str,
        runtime_vendor: str,
        source_surface: str,
    ) -> ConversationEvent:
        return ConversationEvent(
            event_id=event_id,
            project_id=project_id,
            platform=platform,
            source_product=source_product,
            thread_id=thread_id,
            message_id=message_id,
            timestamp_observed=timestamp,
            role="assistant",
            event_type="message_final",
            content_markdown=content,
            capture_adapter="test-adapter@0.1.0",
            runtime_vendor=runtime_vendor,
            source_surface=source_surface,
        )


if __name__ == "__main__":
    unittest.main()
