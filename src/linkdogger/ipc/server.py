"""Local IPC server — JSON over HTTP, bound to localhost.

The server exposes the shared application core (``PeopleService``) so
other local processes can run searches and email exports. Requests are
``POST /rpc`` with a JSON body ``{"method": ..., "params": {...}}``;
responses are ``{"ok": true, "result": ...}`` or
``{"ok": false, "error": ...}``. When ``IPC_TOKEN`` is configured the
client must send ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from linkdogger import __version__
from linkdogger.errors import IPCError
from linkdogger.output.export import emails_payload
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

logger = logging.getLogger(__name__)

JSON = dict


class IPCServer:
    """Threaded JSON-over-HTTP server for local processes."""

    def __init__(
        self,
        service: PeopleService,
        host: str = "127.0.0.1",
        port: int = 8123,
        token: str | None = None,
        backend: str | None = None,
    ) -> None:
        self._service = service
        self._host = host
        self._port = port
        self._token = token
        self._backend = backend
        self._dispatcher = build_dispatcher(service, backend=backend)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving in a background thread."""
        if self._httpd is not None:
            raise IPCError("IPC server already running")
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="linkdogger-ipc"
        )
        self._thread.start()
        logger.info("IPC server listening on %s:%d", self._host, self._port)

    @property
    def port(self) -> int:
        """The port the server is bound to (resolves port 0)."""
        if self._httpd is None:
            return self._port
        return self._httpd.server_address[1]

    def stop(self) -> None:
        """Shut the server down and join its thread."""
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self
        token = self._token
        dispatcher = self._dispatcher

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                logger.debug("ipc request: %s", format % args)

            def do_POST(self) -> None:  # noqa: N802 - HTTP method name
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b""
                try:
                    request = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return self._respond(
                        400, {"ok": False, "error": "invalid JSON body"}
                    )
                if not isinstance(request, dict):
                    return self._respond(
                        400, {"ok": False, "error": "request must be a JSON object"}
                    )
                if token and self.headers.get("Authorization") != f"Bearer {token}":
                    return self._respond(401, {"ok": False, "error": "unauthorized"})
                try:
                    result = server._dispatch(request, dispatcher)
                except IPCError as exc:
                    return self._respond(200, {"ok": False, "error": str(exc)})
                except Exception:
                    logger.exception("IPC method failed")
                    return self._respond(
                        200, {"ok": False, "error": "internal server error"}
                    )
                self._respond(200, {"ok": True, "result": result})

            def _respond(self, status: int, body: JSON) -> None:
                payload = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler

    @staticmethod
    def _dispatch(request: JSON, dispatcher: dict[str, Callable]) -> object:
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(method, str) or method not in dispatcher:
            raise IPCError(
                f"unknown method '{method}' (expected one of "
                f"{', '.join(sorted(dispatcher))})"
            )
        if not isinstance(params, dict):
            raise IPCError("params must be an object")
        return dispatcher[method](**params)


def _sort_key(sort: str | None) -> tuple[SortKey, str] | None:
    if sort is None:
        return None
    try:
        return SortKey.from_option(sort)
    except ValueError:
        return None


def build_dispatcher(
    service: PeopleService, backend: str | None = None
) -> dict[str, Callable]:
    """Map IPC method names to service calls."""

    def ping() -> dict:
        return {"pong": True, "version": __version__}

    def status() -> dict:
        return {"version": __version__, "backend": backend}

    def search(
        company: str,
        sort: str | None = None,
        role: str | None = None,
        location: str | None = None,
        limit: int | None = None,
        provider: str | None = None,
    ) -> dict:
        if provider is not None:
            from linkdogger.services.factory import build_people_service

            search_service = build_people_service(service._settings, provider=provider)
        else:
            search_service = service
        result = search_service.search_company(
            company,
            sort=_sort_key(sort),
            filters=ResultFilters(role=role, location=location),
            limit=limit,
        )
        return result.model_dump(mode="json")

    def export_emails(
        company: str,
        sort: str | None = None,
        role: str | None = None,
        location: str | None = None,
        limit: int | None = None,
        provider: str | None = None,
    ) -> dict:
        if provider is not None:
            from linkdogger.services.factory import build_people_service

            search_service = build_people_service(service._settings, provider=provider)
        else:
            search_service = service
        return emails_payload(
            search_service.search_company(
                company,
                sort=_sort_key(sort),
                filters=ResultFilters(role=role, location=location),
                limit=limit,
            )
        )

    return {
        "ping": ping,
        "status": status,
        "search": search,
        "export_emails": export_emails,
    }
