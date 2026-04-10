"""Tool contract types for widget-centric agent runtime."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ToolDescriptor:
    """Serializable tool metadata exposed to agents."""

    name: str
    category: str
    description: str
    params: Dict[str, Any]


@dataclass
class ToolExecutionResult:
    """Normalized tool execution result contract."""

    success: bool
    message: str
    error: str = ""
    data: Optional[Dict[str, Any]] = None
    state: Optional[Dict[str, Any]] = None
    vega_spec: Optional[Dict[str, Any]] = None


@dataclass
class ToolCallRecord:
    """Trace-friendly tool call record."""

    tool_name: str
    parameters: Dict[str, Any]
    result: ToolExecutionResult


def descriptors_from_openai_tools(openai_tools: List[Dict[str, Any]]) -> List[ToolDescriptor]:
    """Convert OpenAI tool schema list to ToolDescriptor list."""
    out: List[ToolDescriptor] = []
    for tool in openai_tools or []:
        fn = tool.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        out.append(
            ToolDescriptor(
                name=name,
                category="action",
                description=fn.get("description", ""),
                params=fn.get("parameters", {}),
            )
        )
    return out
