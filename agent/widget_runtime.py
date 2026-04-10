"""Widget runtime protocol for protocol kernel."""

from typing import Any, Dict, List, Protocol


class WidgetRuntime(Protocol):
    """Minimal runtime interface consumed by the protocol kernel."""

    def get_observation(self) -> Dict[str, Any]:
        """Return the latest observation snapshot."""

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return available tools for current widget/chart context."""

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one tool call and return raw result."""
