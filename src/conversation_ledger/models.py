from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from conversation_ledger.utils import sha256_text

SCHEMA_VERSION = "conversation_event_v0"
ALLOWED_PLATFORMS = {"claude", "codex", "deepseek", "gemini", "import"}
ALLOWED_ROLES = {"user", "assistant", "system", "tool", "unknown"}
ALLOWED_EVENT_TYPES = {"message_final", "message_revision", "import_record"}


@dataclass(slots=True)
class ConversationEvent:
    event_id: str
    project_id: str
    platform: str
    thread_id: str
    message_id: str
    timestamp_observed: str
    role: str
    event_type: str
    content_markdown: str
    capture_adapter: str
    model_family: str | None = None
    parent_message_id: str | None = None
    content_sha256: str | None = None
    attachment_refs: list[dict[str, Any]] = field(default_factory=list)
    source_url: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version: {self.schema_version}")
        if self.platform not in ALLOWED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {self.platform}")
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"Unsupported role: {self.role}")
        if self.event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unsupported event_type: {self.event_type}")
        if not self.event_id or not self.project_id or not self.thread_id or not self.message_id:
            raise ValueError("event_id, project_id, thread_id, and message_id are required")
        if not self.capture_adapter:
            raise ValueError("capture_adapter is required")
        if self.content_sha256 is None:
            self.content_sha256 = sha256_text(self.content_markdown)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConversationEvent":
        return cls(
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
            event_id=payload["event_id"],
            project_id=payload["project_id"],
            platform=payload["platform"],
            model_family=payload.get("model_family"),
            thread_id=payload["thread_id"],
            message_id=payload["message_id"],
            parent_message_id=payload.get("parent_message_id"),
            timestamp_observed=payload["timestamp_observed"],
            role=payload["role"],
            event_type=payload["event_type"],
            content_markdown=payload.get("content_markdown", ""),
            content_sha256=payload.get("content_sha256"),
            attachment_refs=list(payload.get("attachment_refs", [])),
            source_url=payload.get("source_url"),
            capture_adapter=payload["capture_adapter"],
        )

