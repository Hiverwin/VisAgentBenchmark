"""Framework protocol runner used by benchmark protocol mode."""

from dataclasses import dataclass
import copy
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from agent.loop import AgentLoop
from agent.runners.result_normalizer import normalize_runner_result
from agent.protocol_kernel import (
    append_phase,
    build_step_record,
    compose_verify_summary,
    dedupe_insights,
    derive_final_answer,
)
from agent.tool_contract import descriptors_from_openai_tools
from agent.runtime_backends import MCPWidgetRuntime, RuntimeSnapshot
from agent.schemas import AgentKnowledge, AgentObservation


@dataclass
class ProtocolRunnerDeps:
    build_round_user_message: Callable[..., Dict[str, Any]]
    parse_json_from_response: Callable[[str], Dict[str, Any]]
    extract_answer_from_text: Callable[[str], Dict[str, Any]]
    normalize_json_result: Callable[[str], Dict[str, Any]]
    get_analysis_prompt: Callable[[bool], str]
    get_image_only_analysis_prompt: Callable[[bool], str]
    extract_final_state: Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Dict[str, Any]]
    strip_data_values: Callable[[Dict[str, Any]], Dict[str, Any]]
    save_image_from_base64: Callable[[str, Path], str]
    protocol_verify_instruction: str
    protocol_reason: str
    tool_analysis_keys: List[str]
    deterministic_verify_tool_result: Optional[Callable[[str, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None
    perceptual_verify_if_needed: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None


class ProtocolAgentRunner:
    """Shared protocol loop for framework agent benchmark runs."""

    def __init__(self, deps: ProtocolRunnerDeps):
        self.deps = deps

    def _early_error_result(
        self,
        *,
        qid: str,
        question_text: str,
        task_type: Optional[str],
        stop_reason: str,
        error: str,
        vega_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = {
            "qid": qid,
            "question": question_text,
            "success": False,
            "error": error,
            "answer": "",
            "question_type": "unknown",
            "task_type": task_type,
            "key_insights": [],
            "reasoning_rounds": [],
            "reasoning": "",
            "tool_calls": [],
            "step_trace": [],
            "phase_trace": [],
            "verify_trace": [],
            "stop_reason": stop_reason,
            "degraded_completion": True,
            "final_spec": self.deps.strip_data_values(vega_spec),
            "iterations": 0,
        }
        return normalize_runner_result(result=result, source="protocol_agent")

    async def run(
        self,
        *,
        mcp_session,
        client,
        config,
        openai_tools: List[Dict[str, Any]],
        question: Dict[str, Any],
        vega_spec: Dict[str, Any],
        chart_type: str,
        input_mode: str,
        output_dir: Optional[Path],
        max_iterations: int,
        vega_service,
        system_prompt: str,
        initial_prompt: str,
    ) -> Dict[str, Any]:
        question_text = question.get("question", "")
        qid = question.get("qid", "unknown")
        gt = question.get("ground_truth") or {}

        render_result = vega_service.render(vega_spec)
        if not render_result.get("success"):
            return self._early_error_result(
                qid=qid,
                question_text=question_text,
                task_type=gt.get("task_type"),
                stop_reason="render_failed",
                error=f"Render failed: {render_result.get('error')}",
                vega_spec=vega_spec,
            )

        current_spec = copy.deepcopy(vega_spec)
        current_state = self.deps.extract_final_state(current_spec)
        current_image = render_result["image_base64"]
        if mcp_session is None:
            return self._early_error_result(
                qid=qid,
                question_text=question_text,
                task_type=gt.get("task_type"),
                stop_reason="no_mcp_session",
                error="MCP session is required for protocol runtime",
                vega_spec=vega_spec,
            )

        runtime = MCPWidgetRuntime(
            mcp_session=mcp_session,
            snapshot=RuntimeSnapshot(spec=current_spec, state=current_state, image_base64=current_image),
            vega_service=vega_service,
            extract_final_state=self.deps.extract_final_state,
            tool_analysis_keys=self.deps.tool_analysis_keys,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            self.deps.build_round_user_message(
                input_mode=input_mode,
                base_text=initial_prompt,
                current_spec=current_spec,
                current_state=current_state,
                current_image=current_image,
                model_name=config.model,
            ),
        ]

        all_tool_calls: List[Dict[str, Any]] = []
        all_reasoning_rounds: List[Dict[str, Any]] = []
        all_insights: List[str] = []
        phase_trace: List[Dict[str, Any]] = []
        verify_trace: List[Dict[str, Any]] = []
        step_trace: List[Dict[str, Any]] = []
        final_answer = ""
        question_type = "subjective"
        tool_choice_val = {"type": "auto"} if getattr(config, "tool_choice_format", None) == "dict" else "auto"
        stop_reason = "max_iterations"
        tool_registry = [
            {
                "name": d.name,
                "category": d.category,
                "description": d.description,
                "params": d.params,
            }
            for d in descriptors_from_openai_tools(openai_tools or [])
        ]
        agent_knowledge = AgentKnowledge(
            system_prompt=system_prompt,
            tool_registry=tool_registry,
            chart_specific_usage=str(chart_type),
        )

        loop = AgentLoop(max_iterations=max_iterations)
        model_name_lower = str(getattr(config, "model", "") or "").lower()
        is_claude_family = ("claude" in model_name_lower) or ("anthropic" in model_name_lower)
        claude_continuation_prompt = (
            "Continue from the latest verified state. "
            "If additional actions are needed, call the next tool. "
            "Otherwise return final JSON with a non-empty answer."
        )

        for i in range(max_iterations):
            print(f"    [{qid}] Protocol round {i+1}...")
            round_verify_records: List[Dict[str, Any]] = []
            if is_claude_family and messages and messages[-1].get("role") != "user":
                # Anthropic on some providers rejects requests ending with assistant prefill.
                messages.append({"role": "user", "content": claude_continuation_prompt})

            kwargs = {"model": config.model, "messages": messages, "temperature": config.temperature}
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = tool_choice_val
            try:
                response1 = client.chat.completions.create(**kwargs)
            except Exception as e:
                print(f"      API error: {e}")
                stop_reason = "api_error"
                break
            if not response1 or not response1.choices:
                stop_reason = "empty_response"
                break

            message1 = response1.choices[0].message
            content1 = (message1.content or "").rstrip()
            assistant_content = "" if input_mode == "image_only" else content1
            assistant_msg = {"role": "assistant", "content": assistant_content}
            if message1.tool_calls:
                plan_tc = message1.tool_calls[0]
                plan_tool_name = plan_tc.function.name
                try:
                    plan_tool_args = json.loads(plan_tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    plan_tool_args = {}
                plan_output = {"tool_name": plan_tool_name, "tool_args": plan_tool_args, "stop_or_continue": "continue"}
            else:
                plan_output = self.deps.normalize_json_result(content1) or {"stop_or_continue": "stop", "content_preview": content1[:200]}
            observe_output = self.deps.normalize_json_result(content1) if content1 else {}
            if not observe_output and content1:
                observe_output = {"observation": content1[:300]}
            append_phase(phase_trace, iteration=i + 1, phase="observe", output=observe_output)
            append_phase(phase_trace, iteration=i + 1, phase="plan", output=plan_output)
            obs = runtime.get_observation()
            current_state = obs.get("widget_state", current_state)
            current_image = obs.get("rendered_view", current_image)
            agent_observation = AgentObservation(
                user_query=question_text,
                widget_state=current_state,
                rendered_view=current_image,
            )
            step_record: Dict[str, Any] = build_step_record(
                iteration=i + 1,
                observe_output=observe_output,
                plan_output=plan_output,
                observation_context={
                    "user_query": agent_observation.user_query,
                    "widget_state": agent_observation.widget_state,
                    "rendered_view": agent_observation.rendered_view,
                },
                knowledge_context={
                    "system_prompt": agent_knowledge.system_prompt,
                    "tool_registry": agent_knowledge.tool_registry,
                    "chart_specific_usage": agent_knowledge.chart_specific_usage,
                },
            )
            if message1.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message1.tool_calls
                ]
            messages.append(assistant_msg)

            if message1.tool_calls:
                for tool_call in message1.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments or "{}")
                    print(f"      Tool: {tool_name}")
                    runtime_result = await runtime.execute_tool(tool_name, tool_args)
                    tool_result = runtime_result.get("tool_result", {})
                    tool_msg = runtime_result.get("tool_message", "")
                    analysis_data = runtime_result.get("analysis_data", {}) or {}
                    prev_spec = runtime_result.get("prev_spec", current_spec)
                    current_spec = runtime_result.get("current_spec", current_spec)
                    current_state = runtime_result.get("current_state", current_state)
                    current_image = runtime_result.get("current_image", current_image)
                    if runtime_result.get("state_updated"):
                        print("      View updated")

                    verify_result = {"passed": tool_result.get("success", False), "mode": "tool_success", "message": ""}
                    if self.deps.deterministic_verify_tool_result:
                        verify_result = self.deps.deterministic_verify_tool_result(
                            tool_name,
                            tool_args,
                            tool_result,
                            prev_spec,
                            current_spec,
                        )
                        if (
                            self.deps.perceptual_verify_if_needed
                            and not verify_result.get("passed", False)
                            and input_mode != "text_only"
                        ):
                            verify_result = await self.deps.perceptual_verify_if_needed(
                                client=client,
                                config=config,
                                input_mode=input_mode,
                                current_spec=current_spec,
                                current_state=current_state,
                                current_image=current_image,
                                question_text=question_text,
                                expected_observation=tool_msg or tool_name,
                                deterministic_verify=verify_result,
                            )
                    verify_record = {
                        "iteration": i + 1,
                        "tool_name": tool_name,
                        "verify": verify_result,
                    }
                    verify_trace.append(verify_record)
                    round_verify_records.append(verify_record)
                    step_record["verify"].append(verify_record)
                    append_phase(phase_trace, iteration=i + 1, phase="verify", output=verify_record)

                    call_record = {
                        "tool_name": tool_name,
                        "parameters": tool_args,
                        "result": {
                            "success": tool_result.get("success", False),
                            "message": tool_msg,
                            "error": tool_result.get("error", ""),
                            "data": analysis_data or {},
                        },
                    }
                    all_tool_calls.append(call_record)
                    step_record["tool_calls"].append(call_record)
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": tool_result.get("success", False),
                            "message": tool_msg,
                            "error": tool_result.get("error", ""),
                        }
                    )
                    if tool_result.get("success"):
                        step_record["state_updated"] = True
                    append_phase(phase_trace, iteration=i + 1, phase="act", output=call_record)
                    tool_response_payload = {
                        "success": tool_result.get("success", False),
                        "message": tool_msg,
                        "error": tool_result.get("error", ""),
                        "data": analysis_data or {},
                    }
                    if tool_result.get("success"):
                        tool_response_payload["vega_state"] = current_state
                    tool_response_content = json.dumps(tool_response_payload, ensure_ascii=False)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_response_content})

            if round_verify_records:
                messages.append(
                    {
                        "role": "user",
                        "content": compose_verify_summary(round_verify_records),
                    }
                )

            is_final = loop.is_final_iteration(i) or (not message1.tool_calls)
            if input_mode == "image_only":
                round_prompt = self.deps.get_image_only_analysis_prompt(is_final=True) if is_final else ""
            else:
                verify_part = f"{self.deps.protocol_verify_instruction}\n\n" if message1.tool_calls else ""
                round_prompt = f"{verify_part}{self.deps.protocol_reason} " + self.deps.get_analysis_prompt(is_final=is_final)
            messages.append(
                self.deps.build_round_user_message(
                    input_mode=input_mode,
                    base_text=round_prompt,
                    current_spec=current_spec,
                    current_state=current_state,
                    current_image=current_image,
                    model_name=config.model,
                )
            )

            try:
                response2 = client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    temperature=config.temperature,
                )
            except Exception:
                try:
                    response2 = client.chat.completions.create(
                        model=config.model,
                        messages=messages,
                        temperature=config.temperature,
                        response_format={"type": "json_object"},
                    )
                except Exception as e2:
                    print(f"      REASON error: {e2}")
                    stop_reason = "reason_error"
                    break

            content2 = (response2.choices[0].message.content or "").strip()
            parsed = self.deps.parse_json_from_response(content2) or self.deps.extract_answer_from_text(content2)
            messages.append({"role": "assistant", "content": content2})

            all_insights.extend(parsed.get("key_insights", []) or [])
            if parsed.get("reasoning"):
                all_reasoning_rounds.append({"iteration": i + 1, "reasoning": parsed.get("reasoning", "")})
            if parsed.get("question_type"):
                question_type = str(parsed.get("question_type", "")).lower()
            if parsed.get("answer") or parsed.get("final_answer"):
                final_answer = str(parsed.get("answer") or parsed.get("final_answer", "")).strip()

            append_phase(phase_trace, iteration=i + 1, phase="reason", output=parsed)
            step_record["reason"] = parsed

            exploration_complete = parsed.get("exploration_complete", False)
            if exploration_complete or is_final:
                if exploration_complete:
                    stop_reason = "exploration_complete"
                elif is_final and final_answer:
                    stop_reason = "final_iteration_with_answer"
                else:
                    stop_reason = "final_iteration_without_answer"
                step_record["stop_signal"] = True
                step_trace.append(step_record)
                print(f"    [{qid}] Protocol done, {i + 1} rounds")
                break
            step_trace.append(step_record)

        unique_insights = dedupe_insights(all_insights)
        final_answer = derive_final_answer(question_type, final_answer, unique_insights)

        final_view_path = ""
        if output_dir:
            view_path = output_dir / "images" / f"{qid}_final.png"
            final_view_path = self.deps.save_image_from_base64(current_image, view_path)

        degraded_completion = stop_reason in {
            "api_error",
            "empty_response",
            "reason_error",
            "max_iterations",
            "final_iteration_without_answer",
        }

        result = {
            "qid": qid,
            "question": question_text,
            "success": True,
            "answer": final_answer,
            "question_type": question_type,
            "task_type": gt.get("task_type"),
            "key_insights": unique_insights,
            "reasoning_rounds": all_reasoning_rounds,
            "reasoning": "\n".join([r["reasoning"] for r in all_reasoning_rounds]),
            "model": config.model,
            "tool_calls": all_tool_calls,
            "step_trace": step_trace,
            "phase_trace": phase_trace,
            "verify_trace": verify_trace,
            "stop_reason": stop_reason,
            "degraded_completion": degraded_completion,
            "final_spec": self.deps.strip_data_values(current_spec),
            "final_state": self.deps.extract_final_state(current_spec, current_state),
            "state_check_fields": gt.get("state_check_fields"),
            "iterations": len(all_reasoning_rounds) or max(1, len(phase_trace) // 5),
            "final_view_path": final_view_path,
        }
        return normalize_runner_result(result=result, source="protocol_agent")

