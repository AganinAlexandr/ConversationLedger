from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conversation_ledger.config import LedgerConfig
from conversation_ledger.exporter import MarkdownExporter
from conversation_ledger.importer import ImportWatcher


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


if __name__ == "__main__":
    unittest.main()
