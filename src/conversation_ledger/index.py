from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from conversation_ledger.models import ConversationEvent


@dataclass(slots=True)
class StoredEvent:
    event: ConversationEvent
    raw_path: str


@dataclass(slots=True)
class SearchWindowEntry:
    event_id: str
    message_id: str
    role: str
    event_type: str
    timestamp_observed: str
    content_markdown: str


@dataclass(slots=True)
class SearchHit:
    query: str
    result_type: str
    project_id: str
    platform: str
    source_product: str | None
    runtime_vendor: str | None
    source_surface: str | None
    thread_id: str
    matched_event_id: str
    matched_message_id: str
    timestamp_observed: str
    score: float
    match_reason: list[str]
    raw_path: str
    window: list[SearchWindowEntry]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["window"] = [asdict(entry) for entry in self.window]
        return payload


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
                    source_product TEXT,
                    thread_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    parent_message_id TEXT,
                    timestamp_observed TEXT NOT NULL,
                    role TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    model_family TEXT,
                    runtime_vendor TEXT,
                    source_surface TEXT,
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
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    event_id UNINDEXED,
                    project_id,
                    platform,
                    source_product,
                    runtime_vendor,
                    source_surface,
                    thread_id,
                    content_markdown,
                    tokenize = 'unicode61'
                );
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
            self._ensure_column(connection, "events", "source_product", "TEXT")
            self._ensure_column(connection, "events", "runtime_vendor", "TEXT")
            self._ensure_column(connection, "events", "source_surface", "TEXT")
            connection.execute(
                """
                INSERT INTO events_fts (
                    event_id, project_id, platform, source_product, runtime_vendor, source_surface, thread_id, content_markdown
                )
                SELECT
                    e.event_id, e.project_id, e.platform, e.source_product, e.runtime_vendor, e.source_surface,
                    e.thread_id, e.content_markdown
                FROM events e
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM events_fts f
                    WHERE f.event_id = e.event_id
                )
                """
            )

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

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
                    event_id, project_id, platform, source_product, thread_id, message_id, parent_message_id,
                    timestamp_observed, role, event_type, model_family, runtime_vendor, source_surface, content_markdown,
                    content_sha256, source_url, capture_adapter, raw_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.project_id,
                    event.platform,
                    event.source_product,
                    event.thread_id,
                    event.message_id,
                    event.parent_message_id,
                    event.timestamp_observed,
                    event.role,
                    event.event_type,
                    event.model_family,
                    event.runtime_vendor,
                    event.source_surface,
                    event.content_markdown,
                    event.content_sha256,
                    event.source_url,
                    event.capture_adapter,
                    str(raw_path),
                ),
            )
            connection.execute(
                """
                INSERT INTO events_fts (
                    event_id, project_id, platform, source_product, runtime_vendor, source_surface, thread_id, content_markdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.project_id,
                    event.platform,
                    event.source_product,
                    event.runtime_vendor,
                    event.source_surface,
                    event.thread_id,
                    event.content_markdown,
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

    def fetch_thread_contexts(
        self,
        *,
        project_id: str,
        thread_id: str,
        platform: str | None = None,
        source_product: str | None = None,
        runtime_vendor: str | None = None,
        source_surface: str | None = None,
    ) -> list[dict]:
        with self.session() as connection:
            rows = self._fetch_filtered_rows(
                connection,
                where_clauses=[
                    "project_id = ?",
                    "thread_id = ?",
                ],
                parameters=[
                    project_id,
                    thread_id,
                ],
                platform=platform,
                source_product=source_product,
                runtime_vendor=runtime_vendor,
                source_surface=source_surface,
            )
        return self._group_rows_by_thread(rows)

    def fetch_day_contexts(
        self,
        *,
        project_id: str,
        iso_date: str,
        platform: str | None = None,
        source_product: str | None = None,
        runtime_vendor: str | None = None,
        source_surface: str | None = None,
    ) -> list[dict]:
        with self.session() as connection:
            rows = self._fetch_filtered_rows(
                connection,
                where_clauses=[
                    "project_id = ?",
                    "substr(timestamp_observed, 1, 10) = ?",
                ],
                parameters=[
                    project_id,
                    iso_date,
                ],
                platform=platform,
                source_product=source_product,
                runtime_vendor=runtime_vendor,
                source_surface=source_surface,
            )
        return self._group_rows_by_thread(rows)

    def search_events(
        self,
        query: str,
        project_id: str | None = None,
        platform: str | None = None,
        source_product: str | None = None,
        runtime_vendor: str | None = None,
        source_surface: str | None = None,
        limit: int = 5,
        window: int = 1,
    ) -> list[SearchHit]:
        with self.session() as connection:
            where_clauses = ["events_fts MATCH ?"]
            parameters: list[object] = [query]
            if project_id:
                where_clauses.append("e.project_id = ?")
                parameters.append(project_id)
            if platform:
                where_clauses.append("e.platform = ?")
                parameters.append(platform)
            if source_product:
                where_clauses.append("e.source_product = ?")
                parameters.append(source_product)
            if runtime_vendor:
                where_clauses.append("e.runtime_vendor = ?")
                parameters.append(runtime_vendor)
            if source_surface:
                where_clauses.append("e.source_surface = ?")
                parameters.append(source_surface)
            parameters.append(limit)

            rows = connection.execute(
                f"""
                SELECT
                    e.*,
                    bm25(events_fts, 0.0, 1.0, 0.8, 0.5, 0.5, 1.0, 5.0) AS score
                FROM events_fts
                JOIN events e ON e.event_id = events_fts.event_id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY score, e.timestamp_observed DESC, e.event_id
                LIMIT ?
                """,
                parameters,
            ).fetchall()

            thread_cache: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
            results: list[SearchHit] = []
            for row in rows:
                cache_key = (row["project_id"], row["platform"], row["thread_id"])
                if cache_key not in thread_cache:
                    thread_cache[cache_key] = connection.execute(
                        """
                        SELECT *
                        FROM events
                        WHERE project_id = ? AND platform = ? AND thread_id = ?
                        ORDER BY timestamp_observed, event_id
                        """,
                        cache_key,
                    ).fetchall()

                results.append(
                    self._build_search_hit(
                        query=query,
                        row=row,
                        thread_rows=thread_cache[cache_key],
                        window=window,
                        requested_project=project_id,
                        requested_platform=platform,
                        requested_source_product=source_product,
                        requested_runtime_vendor=runtime_vendor,
                        requested_source_surface=source_surface,
                    )
                )
            return results

    def _fetch_filtered_rows(
        self,
        connection: sqlite3.Connection,
        *,
        where_clauses: list[str],
        parameters: list[object],
        platform: str | None = None,
        source_product: str | None = None,
        runtime_vendor: str | None = None,
        source_surface: str | None = None,
    ) -> list[sqlite3.Row]:
        if platform:
            where_clauses.append("platform = ?")
            parameters.append(platform)
        if source_product:
            where_clauses.append("source_product = ?")
            parameters.append(source_product)
        if runtime_vendor:
            where_clauses.append("runtime_vendor = ?")
            parameters.append(runtime_vendor)
        if source_surface:
            where_clauses.append("source_surface = ?")
            parameters.append(source_surface)
        return connection.execute(
            f"""
            SELECT *
            FROM events
            WHERE {' AND '.join(where_clauses)}
            ORDER BY timestamp_observed, event_id
            """,
            parameters,
        ).fetchall()

    def _group_rows_by_thread(self, rows: list[sqlite3.Row]) -> list[dict]:
        grouped: dict[tuple[str, str, str, str | None, str | None, str | None], list[StoredEvent]] = {}
        for row in rows:
            key = (
                row["project_id"],
                row["platform"],
                row["thread_id"],
                row["source_product"] if "source_product" in row.keys() else None,
                row["runtime_vendor"] if "runtime_vendor" in row.keys() else None,
                row["source_surface"] if "source_surface" in row.keys() else None,
            )
            grouped.setdefault(key, []).append(self._row_to_stored_event(row))

        groups: list[dict] = []
        for (
            project_id,
            platform,
            thread_id,
            source_product,
            runtime_vendor,
            source_surface,
        ), events in grouped.items():
            groups.append(
                {
                    "project_id": project_id,
                    "platform": platform,
                    "source_product": source_product,
                    "runtime_vendor": runtime_vendor,
                    "source_surface": source_surface,
                    "thread_id": thread_id,
                    "message_count": len(events),
                    "started_at": events[0].event.timestamp_observed if events else None,
                    "ended_at": events[-1].event.timestamp_observed if events else None,
                    "events": events,
                }
            )
        groups.sort(key=lambda item: (item["started_at"] or "", item["thread_id"]))
        return groups

    def _row_to_stored_event(self, row: sqlite3.Row) -> StoredEvent:
        event = ConversationEvent(
            schema_version=row["schema_version"] if "schema_version" in row.keys() else "conversation_event_v0",
            event_id=row["event_id"],
            project_id=row["project_id"],
            platform=row["platform"],
            source_product=row["source_product"] if "source_product" in row.keys() else None,
            runtime_vendor=row["runtime_vendor"] if "runtime_vendor" in row.keys() else None,
            model_family=row["model_family"],
            source_surface=row["source_surface"] if "source_surface" in row.keys() else None,
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

    def _build_search_hit(
        self,
        query: str,
        row: sqlite3.Row,
        thread_rows: list[sqlite3.Row],
        window: int,
        requested_project: str | None,
        requested_platform: str | None,
        requested_source_product: str | None,
        requested_runtime_vendor: str | None,
        requested_source_surface: str | None,
    ) -> SearchHit:
        match_index = next(
            index for index, candidate in enumerate(thread_rows) if candidate["event_id"] == row["event_id"]
        )
        start = max(0, match_index - window)
        end = min(len(thread_rows), match_index + window + 1)
        window_rows = thread_rows[start:end]
        window_entries = [
            SearchWindowEntry(
                event_id=item["event_id"],
                message_id=item["message_id"],
                role=item["role"],
                event_type=item["event_type"],
                timestamp_observed=item["timestamp_observed"],
                content_markdown=item["content_markdown"],
            )
            for item in window_rows
        ]

        reasons = [f"fts: {term}" for term in query.replace('"', "").split()[:5]]
        if requested_project and requested_project == row["project_id"]:
            reasons.append("project exact match")
        if requested_platform and requested_platform == row["platform"]:
            reasons.append("platform family exact match")
        if requested_source_product and requested_source_product == row["source_product"]:
            reasons.append("source product exact match")
        if requested_runtime_vendor and requested_runtime_vendor == row["runtime_vendor"]:
            reasons.append("runtime vendor exact match")
        if requested_source_surface and requested_source_surface == row["source_surface"]:
            reasons.append("source surface exact match")

        return SearchHit(
            query=query,
            result_type="message_window",
            project_id=row["project_id"],
            platform=row["platform"],
            source_product=row["source_product"],
            runtime_vendor=row["runtime_vendor"],
            source_surface=row["source_surface"],
            thread_id=row["thread_id"],
            matched_event_id=row["event_id"],
            matched_message_id=row["message_id"],
            timestamp_observed=row["timestamp_observed"],
            score=abs(float(row["score"])),
            match_reason=reasons,
            raw_path=row["raw_path"],
            window=window_entries,
        )
