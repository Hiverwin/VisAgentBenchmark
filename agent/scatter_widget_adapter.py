"""MCP-based scatter widget adapter."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from state_manager import StateManager

from agent.widget_adapter import BaseWidgetAdapter, WidgetSnapshot
from agent.widget_runtime import WidgetRuntime


@dataclass
class ScatterWidgetConfig:
    """Runtime behavior options for MCP scatter adapter."""

    chart_type: str = "scatter_plot"


class ScatterWidgetAdapter(BaseWidgetAdapter, WidgetRuntime):
    """Scatter widget runtime that executes tools through MCP."""

    def __init__(
        self,
        *,
        mcp_session: Any,
        vega_spec: Dict[str, Any],
        image_base64: str = "",
        available_tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[ScatterWidgetConfig] = None,
    ):
        state, _ = StateManager.split(vega_spec)
        super().__init__(WidgetSnapshot(spec=vega_spec, state=state, image_base64=image_base64))
        self.mcp_session = mcp_session
        self.config = config or ScatterWidgetConfig()
        self._available_tools = available_tools or []
        self._last_interaction: Dict[str, Any] = {}

    def get_observation(self) -> Dict[str, Any]:
        return {
            "widget_state": self.get_state(),
            "rendered_view": self.get_image(),
            "chart_type": self.config.chart_type,
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self._available_tools)

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        before_transform = list(self.get_spec().get("transform", []) or [])
        mcp_args = {**(tool_args or {}), "vega_spec": self.get_spec()}
        mcp_result = await self.mcp_session.call_tool(name=tool_name, arguments=mcp_args)

        result: Dict[str, Any] = {}
        if mcp_result.content:
            for content_item in mcp_result.content:
                if getattr(content_item, "type", "") == "text":
                    try:
                        result = json.loads(content_item.text)
                    except json.JSONDecodeError:
                        result = {"success": False, "message": content_item.text}

        updated_spec = result.get("vega_spec") if isinstance(result, dict) else None
        spec_updated = bool(result.get("success")) and isinstance(updated_spec, dict)
        if spec_updated:
            updated_state, _ = StateManager.split(updated_spec)
            self.update(spec=updated_spec, state=updated_state, image_base64=self.get_image())

        after_transform = list(self.get_spec().get("transform", []) or [])
        self._last_interaction = {
            "tool_name": tool_name,
            "success": bool(result.get("success")),
            "spec_updated": spec_updated,
            "transform_count_before": len(before_transform),
            "transform_count_after": len(after_transform),
            "message": result.get("message", ""),
        }
        return result

    def get_last_interaction(self) -> Dict[str, Any]:
        return dict(self._last_interaction)
