"""Protocol-kernel helpers extracted from thick runners.

This module intentionally keeps pure data-flow utilities with no IO side effects.
"""

from typing import Any, Dict, List


def append_phase(phase_trace: List[Dict[str, Any]], *, iteration: int, phase: str, output: Dict[str, Any]) -> None:
    """Append a normalized phase record."""
    phase_trace.append({"iteration": iteration, "phase": phase, "output": output})


def build_step_record(
    *,
    iteration: int,
    observe_output: Dict[str, Any],
    plan_output: Dict[str, Any],
    observation_context: Dict[str, Any],
    knowledge_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Create protocol step record with stable fields."""
    return {
        "iteration": iteration,
        "observe": observe_output,
        "plan": plan_output,
        "act": [],
        "verify": [],
        "reason": {},
        "observation_context": observation_context,
        "knowledge_context": knowledge_context,
        "tool_calls": [],
        "state_updated": False,
        "stop_signal": False,
    }


def compose_verify_summary(round_verify_records: List[Dict[str, Any]]) -> str:
    """Build human-readable verification summary appended to next prompt."""
    verify_lines = [
        f"- {r['tool_name']}: passed={r['verify'].get('passed', False)}, "
        f"mode={r['verify'].get('mode', '')}, message={r['verify'].get('message', '')}"
        for r in round_verify_records
    ]
    return "Verification summary after actions:\n" + "\n".join(verify_lines)


def dedupe_insights(insights: List[str]) -> List[str]:
    """Drop empty/duplicate insights while preserving order."""
    return list(dict.fromkeys([x for x in (insights or []) if x]))


def derive_final_answer(question_type: str, final_answer: str, insights: List[str]) -> str:
    """Derive fallback final answer from insights when answer is missing."""
    answer = str(final_answer or "").strip()
    if answer:
        return answer

    normalized_type = (question_type or "subjective").lower()
    if normalized_type == "objective" and insights:
        first = insights[0]
        if len(first.split()) <= 5:
            return first
    if normalized_type == "subjective" and insights:
        return " ".join(insights)
    return ""
