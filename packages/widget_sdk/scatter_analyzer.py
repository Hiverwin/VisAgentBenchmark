"""Importable widget analyzer (MCP protocol mode)."""

from typing import Any, Dict, List, Optional

from benchmark.config import get_model_config
from benchmark.run_benchmark_protocol import (
    convert_mcp_tools_to_openai_format,
    create_client,
    run_protocol_va_with_mcp,
)
from core.vega_service import get_vega_service
from config.chart_types import ChartType, get_candidate_chart_types
from state_manager import StateManager

from packages.agent_kernel import MCPWidgetRuntime, RuntimeSnapshot
from packages.widget_sdk.contracts import AnalysisResult, new_request_id
from packages.widget_sdk.mcp_bridge import MCPBridge

DEFAULT_AGENT_MODEL_NAME = "gpt_protocol"


def _extract_state(spec: Dict[str, Any], _state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state, _ = StateManager.split(spec)
    return state


def _infer_chart_type(vega_spec: Dict[str, Any], chart_type: Optional[str] = None) -> str:
    if chart_type:
        return str(ChartType.from_string(chart_type))
    candidates = get_candidate_chart_types(vega_spec or {})
    if not candidates:
        return str(ChartType.UNKNOWN)
    return str(candidates[0])


class WidgetAgentAnalyzer:
    """Importable MCP analyzer for any supported widget/chart type."""

    def __init__(
        self,
        *,
        vega_spec: Dict[str, Any],
        chart_type: Optional[str] = None,
        bridge: Optional[MCPBridge] = None,
    ):
        self.initial_spec = vega_spec
        self.chart_type = _infer_chart_type(vega_spec, chart_type)
        self.bridge = bridge or MCPBridge()
        self.runtime: Optional[MCPWidgetRuntime] = None
        self.tools: List[Dict[str, Any]] = []

    async def __aenter__(self) -> "ScatterAgentAnalyzer":
        await self.bridge.__aenter__()
        self.tools = await self.bridge.list_tools()
        render = get_vega_service().render(self.initial_spec)
        image = render.get("image_base64", "")
        self.runtime = MCPWidgetRuntime(
            mcp_session=self.bridge.session,
            snapshot=RuntimeSnapshot(
                spec=self.initial_spec,
                state=_extract_state(self.initial_spec),
                image_base64=image,
            ),
            vega_service=get_vega_service(),
            extract_final_state=_extract_state,
            tool_analysis_keys=["correlation_coefficient", "p_value", "cluster_statistics", "message"],
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.bridge.__aexit__(exc_type, exc, tb)
        self.runtime = None

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self.tools)

    def get_observation(self) -> Dict[str, Any]:
        if self.runtime is None:
            return {}
        obs = self.runtime.get_observation()
        obs["chart_type"] = self.chart_type
        return obs

    async def run(
        self,
        query: str,
        *,
        model_name: Optional[str] = None,
        input_mode: str = "text_and_image",
        max_iterations: int = 6,
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run full protocol agent flow over the scatter widget."""
        if self.runtime is None or self.bridge.session is None:
            raise RuntimeError("Analyzer not initialized. Use 'async with'.")
        resolved_model_name = model_name or DEFAULT_AGENT_MODEL_NAME

        config = get_model_config(resolved_model_name)
        client = create_client(config)
        mcp_tools_response = await self.bridge.session.list_tools()
        openai_tools = convert_mcp_tools_to_openai_format(mcp_tools_response.tools)
        question = {"qid": "external_va_scatter_001", "question": query, "ground_truth": {}}
        result = await run_protocol_va_with_mcp(
            mcp_session=self.bridge.session,
            client=client,
            config=config,
            openai_tools=openai_tools,
            question=question,
            vega_spec=self.runtime.snapshot.spec,
            chart_type=self.chart_type,
            input_mode=input_mode,
            output_dir=None,
            max_iterations=max_iterations,
        )
        observation = self.get_observation()
        final_state = result.get("final_state") or observation.get("widget_state", {})
        final_observation = {
            "widget_state": final_state,
            "rendered_view": observation.get("rendered_view", ""),
            "chart_type": self.chart_type,
        }
        stop_reason = str(result.get("stop_reason", ""))
        degraded = bool(result.get("degraded_completion", False))
        success = bool(result.get("success", True)) and not degraded
        error_message = str(result.get("error", ""))
        if (not success) and (not error_message):
            if stop_reason:
                error_message = f"protocol_incomplete: {stop_reason}"
            else:
                error_message = "protocol_incomplete"
        answer = str(result.get("answer", ""))
        if (not answer) and (not success) and error_message:
            answer = error_message
        return AnalysisResult(
            request_id=request_id or new_request_id(),
            query=query,
            success=success,
            answer=answer,
            tool_calls=result.get("tool_calls", []),
            final_observation=final_observation,
            chart_type=self.chart_type,
            mode="protocol",
            error=error_message,
            stop_reason=stop_reason,
            metadata=metadata or {},
            raw_result=result,
        )


# Backward-compatible alias for existing integrations.
ScatterAnalysisResult = AnalysisResult
ScatterAgentAnalyzer = WidgetAgentAnalyzer
