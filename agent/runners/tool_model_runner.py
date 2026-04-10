"""Tool-using model runner wrappers for benchmark."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from .result_normalizer import normalize_runner_result


@dataclass
class ToolModelRunnerDeps:
    run_single_request_with_responses_mcp: Callable[..., Dict[str, Any]]
    run_multi_turn_with_mcp: Callable[..., Awaitable[Dict[str, Any]]]


class ToolModelRunner:
    """Runner for tool-using models (MCP-based)."""

    def __init__(self, deps: ToolModelRunnerDeps):
        self.deps = deps

    def run_responses_question(
        self,
        *,
        client,
        config,
        question: Dict[str, Any],
        vega_spec: Dict[str, Any],
        chart_type: str,
        remote_mcp_url: str,
        input_mode: str,
        output_dir: Optional[Path],
    ) -> Dict[str, Any]:
        result = self.deps.run_single_request_with_responses_mcp(
            client=client,
            config=config,
            question=question,
            vega_spec=vega_spec,
            chart_type=chart_type,
            remote_mcp_url=remote_mcp_url,
            input_mode=input_mode,
            output_dir=output_dir,
        )
        return normalize_runner_result(result=result, source="responses_mcp")

    async def run_manual_mcp_question(
        self,
        *,
        mcp_session,
        client,
        config,
        openai_tools,
        question: Dict[str, Any],
        vega_spec: Dict[str, Any],
        chart_type: str,
        input_mode: str,
        output_dir: Optional[Path],
        max_iterations: int,
    ) -> Dict[str, Any]:
        result = await self.deps.run_multi_turn_with_mcp(
            mcp_session=mcp_session,
            client=client,
            config=config,
            openai_tools=openai_tools,
            question=question,
            vega_spec=vega_spec,
            chart_type=chart_type,
            input_mode=input_mode,
            output_dir=output_dir,
            max_iterations=max_iterations,
        )
        return normalize_runner_result(result=result, source="manual_mcp")

