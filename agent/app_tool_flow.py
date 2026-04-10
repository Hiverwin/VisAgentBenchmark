"""Shared tool execution flow for app-side modes."""

import copy
from typing import Any, Callable, Dict

from state_manager import DataStore, StateManager


def execute_tool_and_update_view(
    *,
    tool_executor: Any,
    vega_service: Any,
    current_spec: Dict[str, Any],
    current_image: str,
    tool_name: str,
    tool_params: Dict[str, Any],
    context: Dict[str, Any],
    apply_data_manager: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute one tool call and update spec/state/image if needed."""
    current_state, current_data = StateManager.split(current_spec)
    exec_params = dict(tool_params or {})
    DataStore.set(current_data)
    exec_params["state"] = current_state
    if tool_name in ("reset_view", "undo_view"):
        exec_params["context"] = context

    tool_result = tool_executor.execute(tool_name, exec_params)

    tool_execution = {
        "tool_name": tool_name,
        "tool_params": {k: v for k, v in exec_params.items() if k not in ("vega_spec", "context")},
        "tool_result": {k: v for k, v in tool_result.items() if k not in ("vega_spec", "state")},
    }

    out = {
        "status": "failed",
        "tool_result": tool_result,
        "tool_execution": tool_execution,
        "spec": current_spec,
        "state": current_state,
        "image": current_image,
        "message": tool_result.get("message", "") or tool_result.get("error", ""),
        "render_error": "",
    }

    if not tool_result.get("success"):
        return out

    if "vega_spec" not in tool_result:
        out["status"] = "analysis_only"
        return out

    if tool_name not in ("reset_view", "undo_view") and context is not None:
        history = context.setdefault("spec_history", [])
        history.append(copy.deepcopy(current_spec))

    next_spec = tool_result["vega_spec"]
    next_state = tool_result.get("state", current_state)
    next_spec = apply_data_manager(next_spec, context)
    render_result = vega_service.render(next_spec)
    if not render_result.get("success"):
        out["status"] = "render_failed"
        out["render_error"] = render_result.get("error", "Render failed")
        out["spec"] = next_spec
        out["state"] = next_state
        return out

    out["status"] = "state_updated"
    out["spec"] = next_spec
    out["state"] = next_state
    out["image"] = render_result["image_base64"]
    return out

