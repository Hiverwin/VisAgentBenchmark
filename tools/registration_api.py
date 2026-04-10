"""Public registration APIs for extending widget tools at runtime."""

from typing import Any, Callable, Dict, List, Optional

from config.chart_types import ChartType
from .tool_registry import tool_registry


def _normalize_chart_types(chart_types: Optional[List[Any]]) -> Optional[List[ChartType]]:
    if not chart_types:
        return None
    out: List[ChartType] = []
    for ct in chart_types:
        if isinstance(ct, ChartType):
            out.append(ct)
        elif isinstance(ct, str):
            out.append(ChartType.from_string(ct))
        else:
            raise TypeError(f"unsupported chart type value: {ct!r}")
    return out


def register_tool(
    *,
    name: str,
    function: Callable[..., Any],
    category: str = "action",
    description: str = "",
    params: Optional[Dict[str, Any]] = None,
    chart_types: Optional[List[Any]] = None,
    override: bool = False,
) -> None:
    """Register a custom tool for one or multiple widget/chart types."""
    tool_registry.register_tool(
        name=name,
        function=function,
        category=category,
        description=description,
        params=params,
        chart_types=_normalize_chart_types(chart_types),
        override=override,
    )


def register_widget_tool(
    chart_type: Any,
    *,
    name: str,
    function: Callable[..., Any],
    category: str = "action",
    description: str = "",
    params: Optional[Dict[str, Any]] = None,
    override: bool = False,
) -> None:
    """Convenience wrapper to register a tool for a single widget type."""
    register_tool(
        name=name,
        function=function,
        category=category,
        description=description,
        params=params,
        chart_types=[chart_type],
        override=override,
    )


def unregister_tool(name: str) -> bool:
    """Unregister previously-added custom tool."""
    return tool_registry.unregister_tool(name)


def list_custom_tools() -> List[str]:
    """List runtime custom tool names."""
    return tool_registry.list_custom_tools()
