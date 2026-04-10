"""MCP bridge helpers for importable widget SDK."""

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def default_mcp_server_args() -> List[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return [str(repo_root / "chart_tools_mcp_server.py")]


class MCPBridge:
    """Manage MCP stdio session lifecycle for SDK analyzers."""

    def __init__(
        self,
        *,
        command: str = "python",
        args: Optional[List[str]] = None,
    ):
        self.command = command
        self.args = args or default_mcp_server_args()
        self._stack: Optional[AsyncExitStack] = None
        self.session: Optional[ClientSession] = None

    async def __aenter__(self) -> "MCPBridge":
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.command, args=self.args)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self.session = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        if self.session is None:
            return []
        response = await self.session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "params": t.inputSchema or {},
            }
            for t in response.tools
        ]
