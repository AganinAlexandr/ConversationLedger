from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.exporter import MarkdownExporter
from conversation_ledger.importer import ImportWatcher
from conversation_ledger.index import LedgerIndex


class ImportExportTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_import_preserves_original_and_exports_markdown(self) -> None:
        sample = (
            "# Рабочая заметка\n\n"
            "Кириллица сохраняется.\n\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
        )
        source_path = self.config.inbox_path / "daily-note.md"
        source_path.write_text(sample, encoding="utf-8")

        watcher = ImportWatcher(self.config)
        first_result = watcher.import_file(source_path, project_id="sorting-center")
        second_result = watcher.import_file(source_path, project_id="sorting-center")

        self.assertTrue(first_result.imported)
        self.assertTrue(second_result.duplicate)
        self.assertEqual(source_path.read_bytes(), first_result.copied_to.read_bytes())

        exporter = MarkdownExporter(self.config)
        export = exporter.export_thread(
            project_id="sorting-center",
            platform="import",
            thread_id="daily-note",
        )

        exported_text = export.output_path.read_text(encoding="utf-8")
        self.assertIn("Кириллица сохраняется.", exported_text)
        self.assertIn("print('hello')", exported_text)
        self.assertEqual(export.event_count, 1)

    def test_import_codex_thread_snapshot_creates_message_events(self) -> None:
        snapshot = {
            "schemaVersion": 1,
            "thread": {
                "id": "019f184a-54be-7e81-9309-2e5ba967d52d",
                "hostId": "local",
                "title": "Создать ConversationLedger",
            },
            "page": {
                "order": "newest_first",
                "limit": 2,
                "hasMore": False,
            },
            "turns": [
                {
                    "id": "turn-2",
                    "status": "inProgress",
                    "startedAt": 1782862000,
                    "completedAt": None,
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-3",
                            "content": [{"type": "text", "text": "Давай сделаем адаптер именно для Codex."}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-4",
                            "text": "Проверяю доступный формат thread history.",
                            "phase": "commentary",
                        },
                    ],
                },
                {
                    "id": "turn-1",
                    "status": "completed",
                    "startedAt": 1782861000,
                    "completedAt": 1782861010,
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-1",
                            "content": [{"type": "text", "text": "Нужен импорт из чатов Codex."}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-2",
                            "text": "Можно строить импорт по thread snapshot.",
                            "phase": "final_answer",
                        },
                    ],
                },
            ],
        }
        source_path = self.config.inbox_path / "codex-thread.json"
        source_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        watcher = ImportWatcher(self.config)
        first_result = watcher.import_codex_thread_snapshot(source_path, project_id="conversation-ledger")
        second_result = watcher.import_codex_thread_snapshot(source_path, project_id="conversation-ledger")

        self.assertTrue(first_result.imported)
        self.assertEqual(first_result.event_count, 4)
        self.assertEqual(first_result.imported_count, 4)
        self.assertTrue(second_result.duplicate)
        self.assertEqual(source_path.read_bytes(), first_result.copied_to.read_bytes())

        events = LedgerIndex(self.config.db_path).fetch_thread_events(
            project_id="conversation-ledger",
            platform="codex",
            thread_id="019f184a-54be-7e81-9309-2e5ba967d52d",
        )
        self.assertEqual(len(events), 4)
        self.assertEqual(
            [item.event.content_markdown for item in events],
            [
                "Нужен импорт из чатов Codex.",
                "Можно строить импорт по thread snapshot.",
                "Давай сделаем адаптер именно для Codex.",
                "Проверяю доступный формат thread history.",
            ],
        )
        self.assertEqual(
            [item.event.event_type for item in events],
            ["message_final", "message_final", "message_final", "message_revision"],
        )

        exporter = MarkdownExporter(self.config)
        export = exporter.export_thread(
            project_id="conversation-ledger",
            platform="codex",
            thread_id="019f184a-54be-7e81-9309-2e5ba967d52d",
        )
        exported_text = export.output_path.read_text(encoding="utf-8")
        self.assertIn("Нужен импорт из чатов Codex.", exported_text)
        self.assertIn("Проверяю доступный формат thread history.", exported_text)
        self.assertEqual(export.event_count, 4)


if __name__ == "__main__":
    unittest.main()
