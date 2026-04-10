"""Baseline and system-api runner wrappers for benchmark."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from .result_normalizer import normalize_runner_result


@dataclass
class BaselineRunnerDeps:
    run_multi_turn_without_tools: Callable[..., Awaitable[Dict[str, Any]]]
    run_system_api_question: Callable[..., Dict[str, Any]]


class BaselineRunner:
    """Runner for no-tool baseline and system-api modes."""

    def __init__(self, deps: BaselineRunnerDeps):
        self.deps = deps

    async def run_baseline_question(
        self,
        *,
        client,
        config,
        question: Dict[str, Any],
        vega_spec: Dict[str, Any],
        chart_type: str,
        input_mode: str,
        output_dir: Optional[Path],
        max_iterations: int,
    ) -> Dict[str, Any]:
        result = await self.deps.run_multi_turn_without_tools(
            client=client,
            config=config,
            question=question,
            vega_spec=vega_spec,
            chart_type=chart_type,
            input_mode=input_mode,
            output_dir=output_dir,
            max_iterations=max_iterations,
        )
        return normalize_runner_result(result=result, source="baseline")

    def run_system_question(
        self,
        *,
        client,
        config,
        question: Dict[str, Any],
        vega_spec: Dict[str, Any],
        output_dir: Optional[Path],
    ) -> Dict[str, Any]:
        result = self.deps.run_system_api_question(
            client=client,
            config=config,
            question=question,
            vega_spec=vega_spec,
            output_dir=output_dir,
        )
        return normalize_runner_result(result=result, source="system_api")

