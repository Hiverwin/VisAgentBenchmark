"""Custom scatter analyzer factory for external VA systems."""

from typing import Any, Dict

from packages.widget_sdk.custom_widget import create_custom_widget_analyzer
from packages.widget_sdk.scatter_analyzer import ScatterAgentAnalyzer


def create_custom_scatter_analyzer(vega_spec: Dict[str, Any]) -> ScatterAgentAnalyzer:
    """Create analyzer for external custom scatter widget spec (no tool whitelist)."""
    return create_custom_widget_analyzer(vega_spec, chart_type="scatter_plot")
