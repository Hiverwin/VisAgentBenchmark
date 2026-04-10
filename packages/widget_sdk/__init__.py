"""Importable widget SDK entrypoints."""

from packages.widget_sdk.contracts import (
    AnalysisRequest,
    AnalysisResult,
    SessionContinueRequest,
    SessionStartRequest,
)
from packages.widget_sdk.custom_scatter import create_custom_scatter_analyzer
from packages.widget_sdk.preset_scatter import create_preset_scatter_analyzer
from packages.widget_sdk.custom_widget import create_custom_widget_analyzer
from packages.widget_sdk.headless import analyze_widget
from packages.widget_sdk.plugins import (
    WidgetToolPlugin,
    list_custom_tools,
    register_plugin,
    register_tool,
    register_widget_tool,
    unregister_tool,
)
from packages.widget_sdk.preset_widgets import (
    create_preset_widget_analyzer,
    create_preset_bar_analyzer,
    create_preset_line_analyzer,
    create_preset_heatmap_analyzer,
    create_preset_parallel_analyzer,
    create_preset_sankey_analyzer,
)
from packages.widget_sdk.scatter_analyzer import ScatterAgentAnalyzer, ScatterAnalysisResult, WidgetAgentAnalyzer
from packages.widget_sdk.session_api import WidgetAnalysisSession, start_widget_session

__all__ = [
    "AnalysisRequest",
    "AnalysisResult",
    "SessionStartRequest",
    "SessionContinueRequest",
    "analyze_widget",
    "WidgetAnalysisSession",
    "start_widget_session",
    "WidgetToolPlugin",
    "register_plugin",
    "register_tool",
    "register_widget_tool",
    "unregister_tool",
    "list_custom_tools",
    "WidgetAgentAnalyzer",
    "ScatterAgentAnalyzer",
    "ScatterAnalysisResult",
    "create_preset_scatter_analyzer",
    "create_custom_scatter_analyzer",
    "create_custom_widget_analyzer",
    "create_preset_widget_analyzer",
    "create_preset_bar_analyzer",
    "create_preset_line_analyzer",
    "create_preset_heatmap_analyzer",
    "create_preset_parallel_analyzer",
    "create_preset_sankey_analyzer",
]
