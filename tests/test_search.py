from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.search import SearchRequest, run_search
from conversation_ledger.storage import AppendOnlyRawStore


class SearchTests(unittest.TestCase):
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

    def test_scope_all_searches_everything(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="collector", scope="all"),
        )
        platforms = {item["platform"] for item in payload["results"]}
        self.assertGreaterEqual(payload["result_count"], 2)
        self.assertIn("codex", platforms)
        self.assertIn("chatgpt", platforms)

    def test_scope_project_limits_to_one_project(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="collector", scope="project", project_id="alpha"),
        )
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["project_id"], "alpha")

    def test_scope_family_limits_to_one_platform_family(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="collector", scope="family", platform_family="ChatGPT"),
        )
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["platform"], "chatgpt")

    def test_scope_project_family_limits_to_project_and_platform(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(
                query="collector",
                scope="project-family",
                project_id="beta",
                platform_family="codex",
            ),
        )
        self.assertEqual(payload["result_count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["project_id"], "beta")
        self.assertEqual(result["platform"], "codex")

    def test_product_filter_keeps_codex_and_chatgpt_separate(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="beta", scope="all", source_product="codex"),
        )
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["source_product"], "codex")

    def test_vendor_filter_can_group_shared_openai_lineage(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="collector", scope="all", runtime_vendor="openai"),
        )
        products = {item["source_product"] for item in payload["results"]}
        self.assertEqual(payload["result_count"], 3)
        self.assertEqual(products, {"codex", "chatgpt"})

    def test_surface_filter_can_target_cursor_plugin_runs(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(
                query="plugin",
                scope="family",
                platform_family="claude_code",
                source_surface="cursor_claude_code_plugin",
            ),
        )
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["source_surface"], "cursor_claude_code_plugin")

    def test_result_window_contains_neighbor_messages(self) -> None:
        payload = run_search(
            self.index,
            SearchRequest(query="retrieval", scope="project", project_id="alpha", window=1),
        )
        result = payload["results"][0]
        messages = [entry["content_markdown"] for entry in result["window"]]
        self.assertEqual(len(messages), 3)
        self.assertIn("collector baseline", messages[0])
        self.assertIn("retrieval design note", messages[1])
        self.assertIn("final export checklist", messages[2])

    def _seed_events(self) -> None:
        events = [
            self._event(
                event_id="evt-001",
                project_id="alpha",
                platform="codex",
                thread_id="thread-a",
                message_id="msg-001",
                timestamp="2026-06-30T10:00:00Z",
                content="collector baseline",
                source_product="codex",
                runtime_vendor="openai",
                source_surface="browser_web",
            ),
            self._event(
                event_id="evt-002",
                project_id="alpha",
                platform="codex",
                thread_id="thread-a",
                message_id="msg-002",
                timestamp="2026-06-30T10:01:00Z",
                content="retrieval design note",
                source_product="codex",
                runtime_vendor="openai",
                source_surface="browser_web",
            ),
            self._event(
                event_id="evt-003",
                project_id="alpha",
                platform="codex",
                thread_id="thread-a",
                message_id="msg-003",
                timestamp="2026-06-30T10:02:00Z",
                content="final export checklist",
                source_product="codex",
                runtime_vendor="openai",
                source_surface="browser_web",
            ),
            self._event(
                event_id="evt-004",
                project_id="beta",
                platform="chatgpt",
                thread_id="thread-b",
                message_id="msg-004",
                timestamp="2026-06-30T11:00:00Z",
                content="collector search across chatgpt sessions",
                source_product="chatgpt",
                runtime_vendor="openai",
                source_surface="browser_web",
            ),
            self._event(
                event_id="evt-005",
                project_id="beta",
                platform="codex",
                thread_id="thread-c",
                message_id="msg-005",
                timestamp="2026-06-30T12:00:00Z",
                content="collector work for codex project beta",
                source_product="codex",
                runtime_vendor="openai",
                source_surface="browser_web",
            ),
            self._event(
                event_id="evt-006",
                project_id="gamma",
                platform="claude_code",
                thread_id="thread-d",
                message_id="msg-006",
                timestamp="2026-06-30T13:00:00Z",
                content="plugin workflow in cursor agent mode",
                source_product="claude_code",
                runtime_vendor="anthropic",
                source_surface="cursor_claude_code_plugin",
            ),
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
        source_product: str | None = None,
        runtime_vendor: str | None = None,
        source_surface: str | None = None,
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
