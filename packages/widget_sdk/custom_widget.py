"""Custom widget analyzer factory for all supported chart types."""

from typing import Any, Dict, Optional

from packages.widget_sdk.scatter_analyzer import WidgetAgentAnalyzer


def create_custom_widget_analyzer(
    vega_spec: Dict[str, Any],
    *,
    chart_type: Optional[str] = None,
) -> WidgetAgentAnalyzer:
    """Create analyzer for external custom widget spec (no tool whitelist)."""
    return WidgetAgentAnalyzer(vega_spec=vega_spec, chart_type=chart_type)

