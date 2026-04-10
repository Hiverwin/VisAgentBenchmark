"""App-side runner entry that centralizes mode dispatch."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class AppRunnerDeps:
    run_chitchat: Callable[[str, str, Dict[str, Any], Optional[Callable[[str, Dict[str, Any]], None]]], Dict[str, Any]]
    run_goal: Callable[
        [str, Dict[str, Any], str, Any, Dict[str, Any], bool, Optional[Callable[[str, Dict[str, Any]], None]]],
        Dict[str, Any],
    ]
    run_explore: Callable[
        [str, Dict[str, Any], str, Any, Dict[str, Any], Optional[Callable[[str, Dict[str, Any]], None]]],
        Dict[str, Any],
    ]


class AppAgentRunner:
    """Thin wrapper for app-side execution path."""

    def __init__(self, deps: AppRunnerDeps):
        self.deps = deps

    def run_chitchat(
        self,
        user_query: str,
        current_image: str,
        session: Dict[str, Any],
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        return self.deps.run_chitchat(user_query, current_image, session, event_callback)

    def run_goal_oriented(
        self,
        user_query: str,
        vega_spec: Dict[str, Any],
        current_image: str,
        chart_type: Any,
        session: Dict[str, Any],
        benchmark_mode: bool = False,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        return self.deps.run_goal(user_query, vega_spec, current_image, chart_type, session, benchmark_mode, event_callback)

    def run_autonomous(
        self,
        user_query: str,
        vega_spec: Dict[str, Any],
        current_image: str,
        chart_type: Any,
        session: Dict[str, Any],
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        return self.deps.run_explore(user_query, vega_spec, current_image, chart_type, session, event_callback)

