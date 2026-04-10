"""MCP-only agent kernel package facade."""

from .kernel import (
    append_phase,
    build_step_record,
    compose_verify_summary,
    dedupe_insights,
    derive_final_answer,
)
from .runner import ProtocolAgentRunner, ProtocolRunnerDeps
from .runtime import MCPWidgetRuntime, RuntimeSnapshot

__all__ = [
    "append_phase",
    "build_step_record",
    "compose_verify_summary",
    "dedupe_insights",
    "derive_final_answer",
    "ProtocolAgentRunner",
    "ProtocolRunnerDeps",
    "MCPWidgetRuntime",
    "RuntimeSnapshot",
]

