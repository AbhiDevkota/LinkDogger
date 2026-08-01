"""Local inter-process communication (IPC).

Other processes and scripts on the same machine can talk to LinkDogger
through a small JSON-over-HTTP server bound to localhost, without
re-implementing the discovery pipeline. The MCP server (``mcp_server``)
is the companion protocol for AI assistants; this module is for plain
programmatic callers.
"""

from linkdogger.ipc.client import IPCClient, IPCError
from linkdogger.ipc.server import IPCServer, build_dispatcher

__all__ = ["IPCClient", "IPCError", "IPCServer", "build_dispatcher"]
