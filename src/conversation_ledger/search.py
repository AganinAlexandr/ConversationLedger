from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from conversation_ledger.index import LedgerIndex, SearchHit
from conversation_ledger.platforms import canonicalize_platform


@dataclass(slots=True)
class SearchRequest:
    query: str
    scope: str
    project_id: str | None = None
    platform_family: str | None = None
    source_product: str | None = None
    runtime_vendor: str | None = None
    source_surface: str | None = None
    limit: int = 5
    window: int = 1

    def normalized_platform(self) -> str | None:
        return canonicalize_platform(self.platform_family) if self.platform_family else None

    def validate(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.window < 0:
            raise ValueError("window must be >= 0")

        if self.scope == "all":
            if self.project_id or self.platform_family:
                raise ValueError("scope=all does not accept project or family filters")
            return
        if self.scope == "project":
            if not self.project_id or self.platform_family:
                raise ValueError("scope=project requires --project and does not accept --family")
            return
        if self.scope == "family":
            if not self.platform_family or self.project_id:
                raise ValueError("scope=family requires --family and does not accept --project")
            return
        if self.scope == "project-family":
            if not self.project_id or not self.platform_family:
                raise ValueError("scope=project-family requires both --project and --family")
            return
        raise ValueError(f"Unsupported scope: {self.scope}")


def run_search(index: LedgerIndex, request: SearchRequest) -> dict:
    request.validate()
    platform = request.normalized_platform()
    hits = index.search_events(
        query=request.query,
        project_id=request.project_id,
        platform=platform,
        source_product=request.source_product,
        runtime_vendor=request.runtime_vendor,
        source_surface=request.source_surface,
        limit=request.limit,
        window=request.window,
    )
    return {
        "query": request.query,
        "scope": request.scope,
        "filters": {
            "project_id": request.project_id,
            "platform_family": platform,
            "source_product": request.source_product,
            "runtime_vendor": request.runtime_vendor,
            "source_surface": request.source_surface,
            "limit": request.limit,
            "window": request.window,
        },
        "result_count": len(hits),
        "results": [search_hit_to_dict(hit) for hit in hits],
    }


def search_hit_to_dict(hit: SearchHit) -> dict:
    payload = asdict(hit)
    payload["window"] = [asdict(entry) for entry in hit.window]
    return payload


def render_search_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
