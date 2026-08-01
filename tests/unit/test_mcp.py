"""MCP (Model Context Protocol) stdio server."""

import io
import json

from linkdogger.config.settings import Settings
from linkdogger.mcp_server import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    MCPServer,
    _serve_stdio,
)
from linkdogger.services.factory import build_people_service


def _server() -> MCPServer:
    service = build_people_service(Settings(_env_file=None))
    return MCPServer(service, backend="mock")


def test_initialize_handshake() -> None:
    response = _server().handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["name"] == SERVER_NAME
    assert response["result"]["capabilities"]["tools"] == {}


def test_initialized_notification_gets_no_reply() -> None:
    response = _server().handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert response is None


def test_ping() -> None:
    response = _server().handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert response["result"] == {}


def test_tools_list_exposes_expected_tools() -> None:
    response = _server().handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert names == ["search_company", "export_emails", "get_status"]


def test_call_search_company() -> None:
    response = _server().handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "search_company", "arguments": {"company": "Acme"}},
        }
    )
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["company"]["name"] == "Acme Corporation"
    assert payload["count"] == 3


def test_call_export_emails() -> None:
    response = _server().handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "export_emails",
                "arguments": {"company": "Acme"},
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["count"] == 2
    assert payload["emails"] == [
        "alex.sample@example.com",
        "taylor.sample@example.com",
    ]


def test_call_get_status() -> None:
    response = _server().handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "get_status", "arguments": {}},
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["backend"] == "mock"


def test_call_unknown_tool_marks_error() -> None:
    response = _server().handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    assert response["result"]["isError"] is True


def test_unknown_method_returns_jsonrpc_error() -> None:
    response = _server().handle({"jsonrpc": "2.0", "id": 8, "method": "frobnicate"})
    assert response["error"]["code"] == -32601


def test_serve_stdio_end_to_end() -> None:
    incoming = (
        '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}\n'
        '{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}\n'
        '{"jsonrpc": "2.0", "id": 3, "method": "ping"}\n'
        "\n"
        "not json at all\n"
    )
    output = io.StringIO()
    _serve_stdio(_server(), io.StringIO(incoming), output)
    responses = [json.loads(line) for line in output.getvalue().strip().splitlines()]
    assert [response["id"] for response in responses] == [1, 2, 3]
    assert responses[2]["result"] == {}
