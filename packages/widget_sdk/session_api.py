"""Session-level headless APIs for host VA integrations."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from packages.widget_sdk.contracts import (
    AnalysisResult,
    SessionContinueRequest,
    SessionStartRequest,
)
from packages.widget_sdk.mcp_bridge import MCPBridge
from packages.widget_sdk.scatter_analyzer import (
    DEFAULT_AGENT_MODEL_NAME,
    WidgetAgentAnalyzer,
)


@dataclass
class WidgetAnalysisSession:
    """Long-lived analyzer session for iterative host interactions."""

    session_id: str
    analyzer: WidgetAgentAnalyzer
    model_name: str
    input_mode: str
    max_iterations: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    closed: bool = False

    async def continue_analysis(self, request: SessionContinueRequest) -> AnalysisResult:
        """Continue one agent round in the same widget session."""
        if self.closed:
            raise RuntimeError(f"session already closed: {self.session_id}")
        if request.session_id != self.session_id:
            raise ValueError(
                f"session id mismatch: expected={self.session_id} got={request.session_id}"
            )

        return await self.analyzer.run(
            request.query,
            model_name=request.model_name or self.model_name,
            input_mode=request.input_mode or self.input_mode,
            max_iterations=request.max_iterations or self.max_iterations,
            request_id=request.request_id,
            metadata={**self.metadata, **request.metadata},
        )

    async def close(self) -> None:
        """Release MCP resources for this session."""
        if not self.closed:
            await self.analyzer.__aexit__(None, None, None)
            self.closed = True

    async def cancel(self) -> None:
        """Alias of close(), for host APIs using cancel semantics."""
        await self.close()


async def start_widget_session(
    request: SessionStartRequest,
    *,
    bridge: Optional[MCPBridge] = None,
) -> WidgetAnalysisSession:
    """Start one persistent widget analysis session."""
    analyzer = WidgetAgentAnalyzer(
        vega_spec=request.vega_spec,
        chart_type=request.chart_type,
        bridge=bridge,
    )
    await analyzer.__aenter__()
    return WidgetAnalysisSession(
        session_id=request.session_id,
        analyzer=analyzer,
        model_name=request.model_name or DEFAULT_AGENT_MODEL_NAME,
        input_mode=request.input_mode,
        max_iterations=request.max_iterations,
        metadata=dict(request.metadata),
    )

