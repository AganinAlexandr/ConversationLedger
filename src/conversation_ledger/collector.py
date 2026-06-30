from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from conversation_ledger.config import LedgerConfig
from conversation_ledger.index import LedgerIndex
from conversation_ledger.models import ConversationEvent
from conversation_ledger.storage import AppendOnlyRawStore


class CollectorService:
    def __init__(self, config: LedgerConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.index = LedgerIndex(config.db_path)
        self.store = AppendOnlyRawStore(config.raw_root, self.index)
        self.paused = False

    def make_server(self) -> ThreadingHTTPServer:
        return ThreadingHTTPServer((self.config.collector_host, self.config.collector_port), self._handler())

    def run(self) -> None:
        server = self.make_server()
        server.serve_forever()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "ConversationLedger/0.1.0"

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                if self.path != "/health":
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "paused" if service.paused else "recording",
                        "host": service.config.collector_host,
                        "port": service.config.collector_port,
                        "allow_platforms": list(service.config.allow_platforms),
                    },
                )

            def do_POST(self) -> None:
                if self.path == "/control/pause":
                    self._handle_pause()
                    return
                if self.path == "/events":
                    self._handle_events()
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def _handle_pause(self) -> None:
                if not self._authorized():
                    return
                payload = self._read_json()
                paused = bool(payload.get("paused", False))
                service.paused = paused
                self._send_json(HTTPStatus.OK, {"status": "paused" if paused else "recording"})

            def _handle_events(self) -> None:
                if not self._authorized():
                    return
                if service.paused:
                    self._send_json(HTTPStatus.CONFLICT, {"error": "collector_paused"})
                    return

                payload = self._read_json()
                items = payload if isinstance(payload, list) else payload.get("events", [payload])
                accepted = 0
                duplicates = 0
                errors: list[dict[str, str]] = []

                for item in items:
                    try:
                        event = ConversationEvent.from_dict(item)
                        self._check_allowlists(event)
                        result = service.store.append_event(event)
                        accepted += int(result.accepted)
                        duplicates += int(result.duplicate)
                    except Exception as exc:  # noqa: BLE001
                        errors.append({"event_id": item.get("event_id", "unknown"), "error": str(exc)})

                status = HTTPStatus.OK if not errors else HTTPStatus.MULTI_STATUS
                self._send_json(
                    status,
                    {
                        "accepted": accepted,
                        "duplicates": duplicates,
                        "errors": errors,
                    },
                )

            def _check_allowlists(self, event: ConversationEvent) -> None:
                if service.config.allow_platforms and event.platform not in service.config.allow_platforms:
                    raise ValueError(f"platform_not_allowed: {event.platform}")
                if service.config.allow_projects and event.project_id not in service.config.allow_projects:
                    raise ValueError(f"project_not_allowed: {event.project_id}")

            def _authorized(self) -> bool:
                expected = service.config.collector_token
                if not expected:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "collector_token_not_configured"})
                    return False
                provided = self.headers.get("Authorization", "")
                if provided != f"Bearer {expected}":
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return False
                return True

            def _read_json(self) -> dict[str, Any] | list[dict[str, Any]]:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(content_length)
                return json.loads(payload.decode("utf-8"))

            def _send_json(self, status: HTTPStatus, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Cache-Control", "no-store")

            def log_message(self, format: str, *args: object) -> None:
                return

        return RequestHandler

