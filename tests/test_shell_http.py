from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.models import ConversationEvent
from conversation_ledger.shell import LedgerShellService
from conversation_ledger.storage import AppendOnlyRawStore


class ShellHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.config = LedgerConfig(
            commons_root=root / "commons",
            data_root=root / "commons" / "data" / "conversation_ledger",
            knowledge_root=root / "commons" / "knowledge" / "conversation_ledger",
            output_root=root / "output" / "conversation-ledger",
            collector_host="127.0.0.1",
            collector_port=0,
            shell_host="127.0.0.1",
            shell_port=0,
            collector_token="test-token",
        )
        self.service = LedgerShellService(self.config)
        self._seed_events()
        self.server = self.service.make_server()
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_root_serves_shell_html(self) -> None:
        response, body = self._request("GET", "/")
        self.assertEqual(response.status, 200)
        self.assertIn("Conversation Ledger Shell", body.decode("utf-8"))

    def test_tree_endpoint_returns_grouped_projects(self) -> None:
        response, body = self._request("GET", "/api/tree?project=alpha")
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(len(payload["projects"]), 1)
        self.assertEqual(payload["projects"][0]["project_id"], "alpha")
        self.assertEqual(payload["projects"][0]["products"][0]["source_product"], "codex")

    def test_search_endpoint_returns_hits(self) -> None:
        response, body = self._request("GET", "/api/search?scope=project&project=alpha&query=collector")
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["result_count"], 1)

    def test_day_context_endpoint_returns_threads(self) -> None:
        response, body = self._request("GET", "/api/day-context?project=beta&date=2026-06-30")
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["thread_count"], 2)

    def _seed_events(self) -> None:
        store = AppendOnlyRawStore(self.config.raw_root, self.service.index)
        for event in [
            self._event("evt-001", "alpha", "codex", "thread-a", "msg-001", "2026-06-30T10:00:00Z", "collector baseline", "codex", "openai", "browser_web"),
            self._event("evt-002", "beta", "chatgpt", "thread-b", "msg-002", "2026-06-30T11:00:00Z", "collector notes", "chatgpt", "openai", "browser_web"),
            self._event("evt-003", "beta", "codex", "thread-c", "msg-003", "2026-06-30T12:00:00Z", "day context evidence", "codex", "openai", "browser_web"),
        ]:
            store.append_event(event)

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

    def _request(self, method: str, path: str) -> tuple[object, bytes]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        return response, body


if __name__ == "__main__":
    unittest.main()

