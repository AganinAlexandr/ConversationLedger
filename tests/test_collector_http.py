from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from conversation_ledger.collector import CollectorService
from conversation_ledger.config import LedgerConfig


class CollectorHttpTests(unittest.TestCase):
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
            collector_token="test-token",
        )
        self.service = CollectorService(self.config)
        self.server = self.service.make_server()
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_health_has_cors_and_chatgpt_allowlist(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        self.assertIn("chatgpt", body["allow_platforms"])

    def test_options_preflight_is_supported(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("OPTIONS", "/events")
        response = connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)
        self.assertEqual(response.getheader("Access-Control-Allow-Methods"), "GET, POST, OPTIONS")


if __name__ == "__main__":
    unittest.main()
