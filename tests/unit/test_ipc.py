"""Local IPC server and client."""

import pytest

from linkdogger.config.settings import Settings
from linkdogger.errors import IPCError
from linkdogger.ipc import IPCClient, IPCServer
from linkdogger.services.factory import build_people_service


@pytest.fixture()
def ipc_server() -> IPCServer:
    service = build_people_service(Settings(_env_file=None))
    server = IPCServer(service, host="127.0.0.1", port=0, backend="mock")
    server.start()
    yield server
    server.stop()


def _client(server: IPCServer, token: str | None = None) -> IPCClient:
    return IPCClient(port=server.port, token=token)


def test_ping_roundtrip(ipc_server: IPCServer) -> None:
    assert _client(ipc_server).call("ping")["pong"] is True


def test_status_reports_backend(ipc_server: IPCServer) -> None:
    result = _client(ipc_server).call("status")
    assert result["backend"] == "mock"


def test_search_returns_results(ipc_server: IPCServer) -> None:
    result = _client(ipc_server).call("search", company="Acme")
    assert result["company"]["name"] == "Acme Corporation"
    assert result["count"] == 3


def test_search_respects_limit_and_filters(ipc_server: IPCServer) -> None:
    result = _client(ipc_server).call(
        "search", company="Acme", role="engineer", limit=10
    )
    assert result["count"] == 1
    assert result["results"][0]["position"] == "Software Engineer"


def test_export_emails_returns_payload(ipc_server: IPCServer) -> None:
    result = _client(ipc_server).call("export_emails", company="Acme")
    assert result["count"] == 2
    assert "alex.sample@example.com" in result["emails"]


def test_unknown_method_raises(ipc_server: IPCServer) -> None:
    with pytest.raises(IPCError, match="unknown method"):
        _client(ipc_server).call("bogus")


def test_token_required_when_configured() -> None:
    service = build_people_service(Settings(_env_file=None))
    server = IPCServer(
        service, host="127.0.0.1", port=0, token="secret", backend="mock"
    )
    server.start()
    try:
        with pytest.raises(IPCError, match="unauthorized"):
            _client(server).call("ping")
        assert _client(server, token="secret").call("ping")["pong"] is True
    finally:
        server.stop()


def test_client_reports_unreachable_server() -> None:
    client = IPCClient(port=59999, timeout=1)
    with pytest.raises(IPCError, match="could not reach"):
        client.call("ping")
