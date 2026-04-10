"""Custom scatter tools for extension demos."""

import copy
from typing import Any, Dict, List

from state_manager import DataStore, tool_output


@tool_output
def custom_focus_group(
    state: Dict[str, Any],
    field: str,
    keep_values: List[Any],
) -> Dict[str, Any]:
    """Keep only selected category values by appending a Vega-Lite filter transform."""
    if not field:
        return {"success": False, "error": "field is required"}
    if not keep_values:
        return {"success": False, "error": "keep_values must not be empty"}

    new_state = copy.deepcopy(state)
    transforms = list(new_state.get("transform", []))
    transforms.append({"filter": {"field": field, "oneOf": keep_values}})
    new_state["transform"] = transforms

    values = DataStore.get_values() or []
    before_count = len(values)
    after_count = sum(1 for row in values if row.get(field) in keep_values)

    return {
        "success": True,
        "operation": "custom_focus_group",
        "message": f"Focused {field} in {keep_values}, visible points: {after_count}/{before_count}",
        "vega_state": new_state,
        "focus_field": field,
        "keep_values": keep_values,
        "before_count": before_count,
        "after_count": after_count,
    }
