"""Shared app-side event names and helpers for streaming callbacks."""

from typing import Any, Callable, Dict, Optional


EventCallback = Optional[Callable[[str, Dict[str, Any]], None]]


class AppEvents:
    """Canonical frontend-facing events emitted by backend runtime."""

    PING = "ping"
    ERROR = "error"

    INTENT_RECOGNIZED = "intent.recognized"
    MODE_DETECTED = "mode.detected"
    MODE_SWITCH_SUGGESTED = "mode.switch.suggested"

    ITERATION_STARTED = "iteration.started"
    ITERATION_PHASE = "iteration.phase"
    AGENT_MESSAGE = "agent.message"
    TOOL_STARTED = "tool.started"
    TOOL_FINISHED = "tool.finished"
    VIEW_UPDATED = "view.updated"
    ITERATION_FINISHED = "iteration.finished"

    CLARIFICATION_REQUESTED = "clarification.requested"

    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"

    RUN_STARTED = "run.started"
    RUN_FINISHING = "run.finishing"
    RUN_FINISHED = "run.finished"

    HUMAN_INTERRUPT = "human.interrupt"


def emit_event(callback: EventCallback, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Safely emit one structured event to callback."""
    if callback is None:
        return
    payload = data or {}
    try:
        callback(event_type, payload)
    except Exception:
        # Streaming callbacks must never break the main query execution.
        return

