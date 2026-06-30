from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from conversation_ledger.config import LedgerConfig
from conversation_ledger.context import build_day_context, build_thread_context
from conversation_ledger.index import LedgerIndex
from conversation_ledger.search import SearchRequest, run_search


class LedgerShellService:
    def __init__(self, config: LedgerConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.index = LedgerIndex(config.db_path)
        self.web_root = Path(__file__).with_name("web")

    def make_server(self) -> ThreadingHTTPServer:
        return ThreadingHTTPServer((self.config.shell_host, self.config.shell_port), self._handler())

    def run(self) -> None:
        server = self.make_server()
        server.serve_forever()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "ConversationLedgerShell/0.1.0"

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._serve_static("index.html", "text/html; charset=utf-8")
                    return
                if parsed.path == "/app.css":
                    self._serve_static("app.css", "text/css; charset=utf-8")
                    return
                if parsed.path == "/app.js":
                    self._serve_static("app.js", "application/javascript; charset=utf-8")
                    return
                if parsed.path == "/api/health":
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "status": "ok",
                            "shell_host": service.config.shell_host,
                            "shell_port": service.config.shell_port,
                        },
                    )
                    return
                if parsed.path == "/api/options":
                    self._send_json(HTTPStatus.OK, service.index.list_filter_values())
                    return
                if parsed.path == "/api/tree":
                    self._send_json(HTTPStatus.OK, self._build_tree_payload(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/search":
                    self._send_json(HTTPStatus.OK, self._build_search_payload(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/thread-context":
                    self._send_json(HTTPStatus.OK, self._build_thread_context_payload(parse_qs(parsed.query)))
                    return
                if parsed.path == "/api/day-context":
                    self._send_json(HTTPStatus.OK, self._build_day_context_payload(parse_qs(parsed.query)))
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def _build_tree_payload(self, query: dict[str, list[str]]) -> dict:
                return {
                    "filters": self._current_filters(query),
                    "projects": service.index.list_chat_tree(
                        project_id=self._single(query, "project"),
                        platform=self._single(query, "family"),
                        source_product=self._single(query, "product"),
                        runtime_vendor=self._single(query, "vendor"),
                        source_surface=self._single(query, "surface"),
                    ),
                }

            def _build_search_payload(self, query: dict[str, list[str]]) -> dict:
                request = SearchRequest(
                    query=self._single(query, "query") or "",
                    scope=self._single(query, "scope") or "all",
                    project_id=self._scope_project(query),
                    platform_family=self._scope_family(query),
                    source_product=self._single(query, "product"),
                    runtime_vendor=self._single(query, "vendor"),
                    source_surface=self._single(query, "surface"),
                    limit=int(self._single(query, "limit") or "10"),
                    window=int(self._single(query, "window") or "1"),
                )
                return run_search(service.index, request)

            def _build_thread_context_payload(self, query: dict[str, list[str]]) -> dict:
                project_id = self._require(query, "project")
                thread_id = self._require(query, "thread")
                return build_thread_context(
                    service.index,
                    project_id=project_id,
                    thread_id=thread_id,
                    platform_family=self._single(query, "family"),
                    source_product=self._single(query, "product"),
                    runtime_vendor=self._single(query, "vendor"),
                    source_surface=self._single(query, "surface"),
                )

            def _build_day_context_payload(self, query: dict[str, list[str]]) -> dict:
                project_id = self._require(query, "project")
                iso_date = self._require(query, "date")
                return build_day_context(
                    service.index,
                    project_id=project_id,
                    iso_date=iso_date,
                    platform_family=self._single(query, "family"),
                    source_product=self._single(query, "product"),
                    runtime_vendor=self._single(query, "vendor"),
                    source_surface=self._single(query, "surface"),
                )

            def _scope_project(self, query: dict[str, list[str]]) -> str | None:
                scope = self._single(query, "scope")
                if scope in {"project", "project-family"}:
                    return self._single(query, "project")
                return None

            def _scope_family(self, query: dict[str, list[str]]) -> str | None:
                scope = self._single(query, "scope")
                if scope in {"family", "project-family"}:
                    return self._single(query, "family")
                return None

            def _current_filters(self, query: dict[str, list[str]]) -> dict[str, str | None]:
                return {
                    "project": self._single(query, "project"),
                    "family": self._single(query, "family"),
                    "product": self._single(query, "product"),
                    "vendor": self._single(query, "vendor"),
                    "surface": self._single(query, "surface"),
                }

            def _serve_static(self, filename: str, content_type: str) -> None:
                path = service.web_root / filename
                if not path.exists():
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "static_not_found", "file": filename})
                    return
                body = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _single(self, query: dict[str, list[str]], key: str) -> str | None:
                values = query.get(key)
                if not values:
                    return None
                value = values[0].strip()
                return value or None

            def _require(self, query: dict[str, list[str]], key: str) -> str:
                value = self._single(query, key)
                if not value:
                    raise ValueError(f"missing required query parameter: {key}")
                return value

            def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def handle_one_request(self) -> None:
                try:
                    super().handle_one_request()
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

            def log_message(self, format: str, *args: object) -> None:
                return

        return RequestHandler

