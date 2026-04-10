"""Preset scatter analyzer factory."""

from packages.widget_sdk.preset_widgets import create_preset_scatter_analyzer as _create_preset_scatter_analyzer
from packages.widget_sdk.scatter_analyzer import ScatterAgentAnalyzer


def create_preset_scatter_analyzer() -> ScatterAgentAnalyzer:
    """Create an analyzer with built-in scatter spec and sample data."""
    return _create_preset_scatter_analyzer()
