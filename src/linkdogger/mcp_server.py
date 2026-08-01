"""Minimal Model Context Protocol (MCP) server for LinkDogger.

Speaks the MCP transport directly (JSON-RPC 2.0 over stdio, one JSON
document per line) so AI assistants and MCP clients can drive LinkDogger
searches and email exports without any external SDK. Run it with
``linkdogger mcp`` and point your client at it as a stdio server.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TextIO

from linkdogger import __version__
from linkdogger.output.export import emails_payload
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "linkdogger"

_TOOL_DEFINITIONS = [
    {
        "name": "search_company",
        "description": (
            "Discover publicly discoverable people working at a company "
            "and return their profiles with networking signals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name."},
                "sort": {
                    "type": "string",
                    "description": "followers-desc, networking-score-desc, "
                    "followback-desc, influence-desc or name-asc.",
                },
                "role": {"type": "string", "description": "Role text filter."},
                "location": {"type": "string", "description": "Location text filter."},
                "limit": {"type": "integer", "description": "Max results."},
                "provider": {
                    "type": "string",
                    "description": "linkedin, github, hybrid or mock.",
                },
            },
            "required": ["company"],
        },
    },
    {
        "name": "export_emails",
        "description": (
            "Search a company and return every discovered email address "
            "as a flat list plus per-person context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name."},
                "limit": {"type": "integer", "description": "Max results."},
                "provider": {
                    "type": "string",
                    "description": "linkedin, github, hybrid or mock.",
                },
            },
            "required": ["company"],
        },
    },
    {
        "name": "get_status",
        "description": "Report the LinkDogger version and configured backend.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class MCPServer:
    """Handles MCP JSON-RPC messages; one method per protocol method."""

    def __init__(self, service: PeopleService, backend: str | None = None) -> None:
        self._service = service
        self._backend = backend

    def handle(self, request: dict) -> dict | None:
        """Process one request; ``None`` means notification (no reply)."""
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "params must be an object")
        try:
            if method == "initialize":
                return self._reply(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": __version__},
                    },
                )
            if method in ("notifications/initialized", "notifications/cancelled"):
                return None
            if method == "ping":
                return self._reply(request_id, {})
            if method == "tools/list":
                return self._reply(request_id, {"tools": _TOOL_DEFINITIONS})
            if method == "tools/call":
                return self._call_tool(request_id, params)
            return self._error(request_id, -32601, f"method not found: {method}")
        except Exception:
            logger.exception("MCP request failed")
            return self._error(request_id, -32603, "internal error")

    def _call_tool(self, request_id: object, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "search_company":
            return self._tool_reply(request_id, _run_search(self._service, arguments))
        if name == "export_emails":
            return self._tool_reply(
                request_id, _run_export_emails(self._service, arguments)
            )
        if name == "get_status":
            status = json.dumps(
                {"version": __version__, "backend": self._backend},
                indent=2,
                ensure_ascii=False,
            )
            return self._tool_reply(request_id, status)
        return self._tool_error(request_id, f"unknown tool '{name}'")

    @staticmethod
    def _reply(request_id: object, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _tool_reply(request_id: object, text: str) -> dict:
        return MCPServer._reply(
            request_id,
            {"content": [{"type": "text", "text": text}], "isError": False},
        )

    @staticmethod
    def _tool_error(request_id: object, message: str) -> dict:
        return MCPServer._reply(
            request_id,
            {"content": [{"type": "text", "text": message}], "isError": True},
        )


def _run_search(service: PeopleService, arguments: dict) -> str:
    provider = arguments.get("provider")
    search_service = _with_provider(service, provider)
    sort = arguments.get("sort")
    try:
        sort_key = SortKey.from_option(sort) if sort else None
    except ValueError:
        sort_key = None
    result = search_service.search_company(
        arguments.get("company", ""),
        sort=sort_key,
        filters=ResultFilters(
            role=arguments.get("role"), location=arguments.get("location")
        ),
        limit=arguments.get("limit"),
    )
    return json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)


def _run_export_emails(service: PeopleService, arguments: dict) -> str:
    search_service = _with_provider(service, arguments.get("provider"))
    result = search_service.search_company(
        arguments.get("company", ""),
        limit=arguments.get("limit"),
    )
    return json.dumps(emails_payload(result), indent=2, ensure_ascii=False)


def _with_provider(service: PeopleService, provider: object) -> PeopleService:
    if not provider:
        return service
    from linkdogger.services.factory import build_people_service

    return build_people_service(service._settings, provider=str(provider))


def serve(service: PeopleService, backend: str | None = None) -> int:
    """Serve MCP over stdio on stdin/stdout until EOF. Returns exit code."""
    server = MCPServer(service, backend=backend)
    return _serve_stdio(server, sys.stdin, sys.stdout)


def _serve_stdio(server: MCPServer, input_stream: TextIO, output_stream: TextIO) -> int:
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("dropping non-JSON line from MCP client")
            continue
        response = server.handle(request)
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()
    return 0
