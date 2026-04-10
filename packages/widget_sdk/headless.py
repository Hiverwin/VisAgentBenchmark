"""Headless integration API for host VA systems."""

from typing import Optional

from packages.widget_sdk.contracts import AnalysisRequest, AnalysisResult
from packages.widget_sdk.mcp_bridge import MCPBridge
from packages.widget_sdk.scatter_analyzer import WidgetAgentAnalyzer


async def analyze_widget(
    request: AnalysisRequest,
    *,
    bridge: Optional[MCPBridge] = None,
) -> AnalysisResult:
    """Run one full widget analysis from host-facing request contract."""
    async with WidgetAgentAnalyzer(
        vega_spec=request.vega_spec,
        chart_type=request.chart_type,
        bridge=bridge,
    ) as analyzer:
        return await analyzer.run(
            request.query,
            model_name=request.model_name,
            input_mode=request.input_mode,
            max_iterations=request.max_iterations,
            request_id=request.request_id,
            metadata=request.metadata,
        )

