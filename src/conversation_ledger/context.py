from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from conversation_ledger.index import LedgerIndex, StoredEvent
from conversation_ledger.platforms import canonicalize_platform


@dataclass(slots=True)
class ContextRequest:
    project_id: str
    platform_family: str | None = None
    source_product: str | None = None
    runtime_vendor: str | None = None
    source_surface: str | None = None

    def normalized_platform(self) -> str | None:
        return canonicalize_platform(self.platform_family) if self.platform_family else None


def build_thread_context(
    index: LedgerIndex,
    *,
    project_id: str,
    thread_id: str,
    platform_family: str | None = None,
    source_product: str | None = None,
    runtime_vendor: str | None = None,
    source_surface: str | None = None,
) -> dict:
    request = ContextRequest(
        project_id=project_id,
        platform_family=platform_family,
        source_product=source_product,
        runtime_vendor=runtime_vendor,
        source_surface=source_surface,
    )
    events = index.fetch_thread_contexts(
        project_id=project_id,
        thread_id=thread_id,
        platform=request.normalized_platform(),
        source_product=source_product,
        runtime_vendor=runtime_vendor,
        source_surface=source_surface,
    )
    return {
        "result_type": "thread_context",
        "thread_id": thread_id,
        "filters": {
            "project_id": project_id,
            "platform_family": request.normalized_platform(),
            "source_product": source_product,
            "runtime_vendor": runtime_vendor,
            "source_surface": source_surface,
        },
        "thread_count": len(events),
        "threads": [_group_to_dict(group) for group in events],
    }


def build_day_context(
    index: LedgerIndex,
    *,
    project_id: str,
    iso_date: str,
    platform_family: str | None = None,
    source_product: str | None = None,
    runtime_vendor: str | None = None,
    source_surface: str | None = None,
) -> dict:
    request = ContextRequest(
        project_id=project_id,
        platform_family=platform_family,
        source_product=source_product,
        runtime_vendor=runtime_vendor,
        source_surface=source_surface,
    )
    groups = index.fetch_day_contexts(
        project_id=project_id,
        iso_date=iso_date,
        platform=request.normalized_platform(),
        source_product=source_product,
        runtime_vendor=runtime_vendor,
        source_surface=source_surface,
    )
    return {
        "result_type": "day_context",
        "date": iso_date,
        "filters": {
            "project_id": project_id,
            "platform_family": request.normalized_platform(),
            "source_product": source_product,
            "runtime_vendor": runtime_vendor,
            "source_surface": source_surface,
        },
        "thread_count": len(groups),
        "threads": [_group_to_dict(group) for group in groups],
    }


def render_context_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _group_to_dict(group: dict) -> dict:
    return {
        "project_id": group["project_id"],
        "platform": group["platform"],
        "source_product": group["source_product"],
        "runtime_vendor": group["runtime_vendor"],
        "source_surface": group["source_surface"],
        "thread_id": group["thread_id"],
        "message_count": group["message_count"],
        "started_at": group["started_at"],
        "ended_at": group["ended_at"],
        "events": [_stored_event_to_dict(event) for event in group["events"]],
    }


def _stored_event_to_dict(stored: StoredEvent) -> dict:
    event = stored.event
    return {
        "event_id": event.event_id,
        "message_id": event.message_id,
        "timestamp_observed": event.timestamp_observed,
        "role": event.role,
        "event_type": event.event_type,
        "platform": event.platform,
        "source_product": event.source_product,
        "runtime_vendor": event.runtime_vendor,
        "source_surface": event.source_surface,
        "content_markdown": event.content_markdown,
        "raw_path": stored.raw_path,
    }

