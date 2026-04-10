"""Shared result normalization for benchmark runners."""

from typing import Any, Dict, List


def normalize_runner_result(
    *,
    result: Dict[str, Any],
    source: str,
    default_tool_calls: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Normalize result schema across agent/tool_model/baseline runners."""
    normalized = dict(result or {})
    success = bool(normalized.get("success", False))
    answer = str(normalized.get("answer", "") or "").strip()
    tool_calls = normalized.get("tool_calls")
    if tool_calls is None:
        tool_calls = default_tool_calls or []
        normalized["tool_calls"] = tool_calls

    if "step_trace" not in normalized:
        normalized["step_trace"] = (
            [
                {
                    "iteration": 1,
                    "observe": {"source": source},
                    "plan": {"stop_or_continue": "stop"},
                    "act": [],
                    "verify": [],
                    "reason": {"answer": answer},
                    "tool_calls": tool_calls,
                    "state_updated": False,
                    "stop_signal": True,
                }
            ]
            if success
            else []
        )
    if "phase_trace" not in normalized:
        normalized["phase_trace"] = []
    if "verify_trace" not in normalized:
        normalized["verify_trace"] = []

    if "stop_reason" not in normalized:
        if not success:
            normalized["stop_reason"] = "runtime_error"
        elif answer:
            normalized["stop_reason"] = "completed_with_answer"
        else:
            normalized["stop_reason"] = "completed_without_answer"

    if "degraded_completion" not in normalized:
        normalized["degraded_completion"] = (not success) or (not answer)

    # Expose tool-calling channel for easier benchmark auditing.
    if "tool_call_api" not in normalized:
        if source == "responses_mcp":
            normalized["tool_call_api"] = "responses_api_mcp"
        elif source in {"manual_mcp", "protocol_agent"}:
            normalized["tool_call_api"] = "chat_completions_function_call"
        elif source in {"baseline", "system_api"}:
            normalized["tool_call_api"] = "none"
        else:
            normalized["tool_call_api"] = "unknown"

    return normalized

