"""Host-facing plugin registration APIs for widget tools."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from tools.registration_api import (
    list_custom_tools,
    register_tool,
    register_widget_tool,
    unregister_tool,
)


@dataclass
class WidgetToolPlugin:
    """Declarative plugin spec for registering host tools."""

    name: str
    function: Callable[..., Any]
    category: str = "action"
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    chart_types: Optional[List[Any]] = None
    override: bool = False


def register_plugin(plugin: WidgetToolPlugin) -> None:
    """Register a plugin spec to tool registry."""
    register_tool(
        name=plugin.name,
        function=plugin.function,
        category=plugin.category,
        description=plugin.description,
        params=plugin.params,
        chart_types=plugin.chart_types,
        override=plugin.override,
    )


__all__ = [
    "WidgetToolPlugin",
    "register_plugin",
    "register_tool",
    "register_widget_tool",
    "unregister_tool",
    "list_custom_tools",
]

