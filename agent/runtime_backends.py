"""Runtime backends for protocol runner (MCP only)."""

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from state_manager import StateManager


ExtractStateFn = Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Dict[str, Any]]


@dataclass
class RuntimeSnapshot:
    spec: Dict[str, Any]
    state: Dict[str, Any]
    image_base64: str


class MCPWidgetRuntime:
    """Protocol runtime that executes tools through MCP session."""

    def __init__(
        self,
        *,
        mcp_session: Any,
        snapshot: RuntimeSnapshot,
        vega_service: Any,
        extract_final_state: ExtractStateFn,
        tool_analysis_keys: Optional[List[str]] = None,
    ):
        self.mcp_session = mcp_session
        self.snapshot = snapshot
        self.vega_service = vega_service
        self.extract_final_state = extract_final_state
        self.tool_analysis_keys = tool_analysis_keys or []

    def get_observation(self) -> Dict[str, Any]:
        return {
            "widget_state": self.snapshot.state,
            "rendered_view": self.snapshot.image_base64,
        }

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        prev_spec = copy.deepcopy(self.snapshot.spec)
        mcp_args = {**(tool_args or {}), "vega_spec": self.snapshot.spec}
        mcp_result = await self.mcp_session.call_tool(name=tool_name, arguments=mcp_args)

        tool_result: Dict[str, Any] = {}
        if mcp_result.content:
            for content_item in mcp_result.content:
                if getattr(content_item, "type", "") == "text":
                    try:
                        tool_result = json.loads(content_item.text)
                    except json.JSONDecodeError:
                        tool_result = {"success": False, "message": content_item.text}

        tool_message = tool_result.get("message", "") or tool_result.get("error", "")
        analysis_data = {
            k: tool_result[k]
            for k in self.tool_analysis_keys
            if k in tool_result and tool_result[k] is not None
        }

        state_updated = False
        if tool_result.get("success"):
            updated = tool_result.get("vega_spec") or tool_result.get("vega_state")
            if updated:
                if "data" not in updated or updated.get("data") is None:
                    data = self.snapshot.spec.get("data")
                    if data is not None:
                        updated = StateManager.reconstruct(updated, data)
                self.snapshot.spec = updated
                self.snapshot.state = (
                    tool_result.get("state")
                    if "state" in tool_result
                    else self.extract_final_state(self.snapshot.spec)
                )
                render_result = self.vega_service.render(self.snapshot.spec)
                if render_result.get("success"):
                    self.snapshot.image_base64 = render_result["image_base64"]
                state_updated = True

        return {
            "tool_result": tool_result,
            "tool_message": tool_message,
            "analysis_data": analysis_data,
            "prev_spec": prev_spec,
            "current_spec": self.snapshot.spec,
            "current_state": self.snapshot.state,
            "current_image": self.snapshot.image_base64,
            "state_updated": state_updated,
        }


