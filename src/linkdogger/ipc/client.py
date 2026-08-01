"""Local IPC client — talk to a running LinkDogger IPC server."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from linkdogger.errors import IPCError

DEFAULT_TIMEOUT = 10.0


class IPCClient:
    """Minimal JSON-over-HTTP client for ``linkdogger ipc-serve``."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8123,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._url = f"http://{host}:{port}/rpc"
        self._token = token
        self._timeout = timeout

    def call(self, method: str, **params: object) -> object:
        """Invoke ``method`` with ``params`` and return the result."""
        body = json.dumps({"method": method, "params": params}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            self._url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (ValueError, OSError):
                raise IPCError(f"IPC request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise IPCError(
                f"could not reach the LinkDogger IPC server at {self._url}: {exc}"
            ) from exc
        if not payload.get("ok"):
            raise IPCError(payload.get("error", "IPC request failed"))
        return payload.get("result")
