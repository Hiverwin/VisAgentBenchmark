"""Minimal schemas for framework-aligned agent loop."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AgentObservation:
    """Dynamic context aligned with paper Observation."""

    user_query: str
    widget_state: Dict[str, Any]
    rendered_view: str


@dataclass
class AgentKnowledge:
    """Persistent context aligned with paper Knowledge."""

    system_prompt: str
    tool_registry: List[Dict[str, Any]]
    chart_specific_usage: str

