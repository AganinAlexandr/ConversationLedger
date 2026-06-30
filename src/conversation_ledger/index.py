from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from conversation_ledger.models import ConversationEvent


@dataclass(slots=True)
class StoredEvent:
    event: ConversationEvent
    raw_path: str


class LedgerIndex:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    parent_message_id TEXT,
                    timestamp_observed TEXT NOT NULL,
                    role TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    model_family TEXT,
                    content_markdown TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    source_url TEXT,
                    capture_adapter TEXT NOT NULL,
                    raw_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_events_thread_time
                    ON events(project_id, platform, thread_id, timestamp_observed, event_id);
                CREATE INDEX IF NOT EXISTS idx_events_day
                    ON events(project_id, timestamp_observed);
                CREATE TABLE IF NOT EXISTS imports (
                    import_sha256 TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    copied_to TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def has_event(self, event: ConversationEvent) -> bool:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM events
                WHERE event_id = ?
                   OR (
                        project_id = ?
                    AND platform = ?
                    AND thread_id = ?
                    AND message_id = ?
                    AND event_type = ?
                    AND content_sha256 = ?
                   )
                LIMIT 1
                """,
                (
                    event.event_id,
                    event.project_id,
                    event.platform,
                    event.thread_id,
                    event.message_id,
                    event.event_type,
                    event.content_sha256,
                ),
            ).fetchone()
            return row is not None

    def record_event(self, event: ConversationEvent, raw_path: Path) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, project_id, platform, thread_id, message_id, parent_message_id,
                    timestamp_observed, role, event_type, model_family, content_markdown,
                    content_sha256, source_url, capture_adapter, raw_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.project_id,
                    event.platform,
                    event.thread_id,
                    event.message_id,
                    event.parent_message_id,
                    event.timestamp_observed,
                    event.role,
                    event.event_type,
                    event.model_family,
                    event.content_markdown,
                    event.content_sha256,
                    event.source_url,
                    event.capture_adapter,
                    str(raw_path),
                ),
            )

    def has_import(self, import_sha256: str) -> bool:
        with self.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM imports WHERE import_sha256 = ? LIMIT 1",
                (import_sha256,),
            ).fetchone()
            return row is not None

    def record_import(
        self,
        import_sha256: str,
        source_name: str,
        source_path: Path,
        copied_to: Path,
        thread_id: str,
        project_id: str,
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO imports (
                    import_sha256, source_name, source_path, copied_to, thread_id, project_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    import_sha256,
                    source_name,
                    str(source_path),
                    str(copied_to),
                    thread_id,
                    project_id,
                ),
            )

    def fetch_thread_events(self, project_id: str, platform: str, thread_id: str) -> list[StoredEvent]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM events
                WHERE project_id = ? AND platform = ? AND thread_id = ?
                ORDER BY timestamp_observed, event_id
                """,
                (project_id, platform, thread_id),
            ).fetchall()
        return [self._row_to_stored_event(row) for row in rows]

    def fetch_project_day_events(self, project_id: str, iso_date: str) -> list[StoredEvent]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM events
                WHERE project_id = ? AND substr(timestamp_observed, 1, 10) = ?
                ORDER BY timestamp_observed, event_id
                """,
                (project_id, iso_date),
            ).fetchall()
        return [self._row_to_stored_event(row) for row in rows]

    def _row_to_stored_event(self, row: sqlite3.Row) -> StoredEvent:
        event = ConversationEvent(
            schema_version=row["schema_version"] if "schema_version" in row.keys() else "conversation_event_v0",
            event_id=row["event_id"],
            project_id=row["project_id"],
            platform=row["platform"],
            model_family=row["model_family"],
            thread_id=row["thread_id"],
            message_id=row["message_id"],
            parent_message_id=row["parent_message_id"],
            timestamp_observed=row["timestamp_observed"],
            role=row["role"],
            event_type=row["event_type"],
            content_markdown=row["content_markdown"],
            content_sha256=row["content_sha256"],
            attachment_refs=[],
            source_url=row["source_url"],
            capture_adapter=row["capture_adapter"],
        )
        return StoredEvent(event=event, raw_path=row["raw_path"])
