"""Goal-oriented (cooperative) analysis mode."""
from typing import Callable, Dict, List, Optional
import time
import copy
from dataclasses import asdict
from core.vlm_service import get_vlm_service
from core.vega_service import get_vega_service
from tools import get_tool_executor
from prompts import get_prompt_manager
from config.settings import Settings
from agent.loop import AgentLoop
from agent.app_tool_flow import execute_tool_and_update_view
from agent.schemas import AgentKnowledge, AgentObservation
from core.event_types import AppEvents, emit_event
from core.utils import app_logger, get_spec_data_count
from state_manager import StateManager


class GoalOrientedMode:
    """Goal-oriented analysis mode."""
    
    def __init__(self):
        self.vlm = get_vlm_service()
        self.vega = get_vega_service()
        self.tool_executor = get_tool_executor()
        self.prompt_mgr = get_prompt_manager()

    @staticmethod
    def _selection_brief(selection: Optional[Dict]) -> str:
        if not selection:
            return ""
        summary = selection.get("summary")
        count = selection.get("count")
        predicates = selection.get("predicates") or []
        if summary:
            return f"Selection summary: {summary}"
        if predicates:
            return f"Selection predicates: {predicates}"
        if count is not None:
            return f"Selected points: {count}"
        return "Selection context provided."

    @staticmethod
    def _extract_clarification(decision: Dict) -> Optional[Dict]:
        if not isinstance(decision, dict):
            return None
        direct = decision.get("clarification")
        if isinstance(direct, dict):
            question = str(
                direct.get("question")
                or direct.get("prompt")
                or direct.get("message")
                or ""
            ).strip()
            options = direct.get("options") or direct.get("choices") or []
            if question:
                return {"question": question, "options": options}
        if not decision.get("needs_clarification"):
            return None
        question = str(
            decision.get("clarification_question")
            or decision.get("question")
            or "I need one clarification before continuing."
        ).strip()
        options = decision.get("clarification_options") or decision.get("choices") or []
        return {"question": question, "options": options}

    @staticmethod
    def _extract_spec_title(vega_spec: Optional[Dict]) -> str:
        if not isinstance(vega_spec, dict):
            return ""
        title = vega_spec.get("title")
        if isinstance(title, str):
            return title.strip().lower()
        if isinstance(title, dict):
            text = title.get("text")
            if isinstance(text, str):
                return text.strip().lower()
        return ""

    @staticmethod
    def _is_demo3_clarification_case(user_query: str, vega_spec: Optional[Dict], context: Optional[Dict]) -> bool:
        if (context or {}).get("demo3_case_active"):
            return True
        q = str(user_query or "").lower()
        title = GoalOrientedMode._extract_spec_title(vega_spec)
        query_markers = [
            "dominated by one region",
            "guide me step by step",
            "pick a focus direction",
            "unsure where to start",
            "not sure where to start",
        ]
        return ("weekly incident trend by region" in title) or any(m in q for m in query_markers)

    @staticmethod
    def _emit_guided_clarification(
        event_callback: Optional[Callable[[str, Dict], None]],
        question: str,
        options: List[Dict],
        iteration: int = 1,
    ) -> None:
        emit_event(event_callback, AppEvents.ITERATION_STARTED, {"iteration": iteration})
        emit_event(
            event_callback,
            AppEvents.ITERATION_PHASE,
            {"iteration": iteration, "phase": "observe", "summary": "Read current chart state and query"},
        )
        emit_event(
            event_callback,
            AppEvents.ITERATION_PHASE,
            {"iteration": iteration, "phase": "plan", "summary": "Detected ambiguous objective; clarification needed"},
        )
        emit_event(
            event_callback,
            AppEvents.CLARIFICATION_REQUESTED,
            {
                "iteration": iteration,
                "question": question,
                "options": options,
            },
        )
        emit_event(
            event_callback,
            AppEvents.ITERATION_PHASE,
            {"iteration": iteration, "phase": "reason", "summary": "Waiting for your clarification choice"},
        )
        emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration})

    @staticmethod
    def _goal_plan_snapshot(decision: Dict, user_query: str) -> Dict:
        if not isinstance(decision, dict):
            return {
                "objective": user_query,
                "sub_goal": "",
                "tool_name": None,
                "tool_args": {},
                "goal_achieved": False,
                "goal_gap_note": "No structured plan returned.",
            }
        tool_call = decision.get("tool_call") if isinstance(decision.get("tool_call"), dict) else {}
        objective = str(decision.get("objective") or user_query or "").strip()
        sub_goal = str(
            decision.get("sub_goal")
            or decision.get("next_milestone")
            or decision.get("step_goal")
            or ""
        ).strip()
        tool_name = tool_call.get("tool")
        tool_args = tool_call.get("params", {}) if isinstance(tool_call.get("params"), dict) else {}
        goal_achieved = bool(decision.get("goal_achieved", False))
        if goal_achieved:
            gap_note = "Goal is marked as achieved."
        elif tool_name:
            gap_note = "Need one more operation to close the goal gap."
        else:
            gap_note = "No tool proposed yet; goal gap remains."
        return {
            "objective": objective or user_query,
            "sub_goal": sub_goal,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "goal_achieved": goal_achieved,
            "goal_gap_note": gap_note,
        }

    @staticmethod
    def _goal_plan_summary(plan_snapshot: Dict) -> str:
        if plan_snapshot.get("goal_achieved"):
            return "Planned to stop: explicit goal achieved"
        tool_name = plan_snapshot.get("tool_name")
        if tool_name:
            sub_goal = str(plan_snapshot.get("sub_goal") or "").strip()
            if sub_goal:
                return f"Goal step: {sub_goal} via {tool_name}"
            return f"Goal step: call {tool_name} to reduce objective gap"
        return "Planned to reason without tool; objective gap check pending"
    
    def execute(
        self,
        user_query: str,
        vega_spec: Dict,
        image_base64: str,
        chart_type,
        context: Dict = None,
        benchmark_mode: bool = False,
        event_callback: Optional[Callable[[str, Dict], None]] = None,
    ) -> Dict:
        """Run goal-oriented analysis (multi-turn messages)."""
        if benchmark_mode:
            app_logger.info("Benchmark mode enabled: ANSWER field will be required in final iteration")
        system_prompt = self.prompt_mgr.assemble_system_prompt(
            chart_type=chart_type,
            mode="goal_oriented",
            include_tools=True,
            benchmark_mode=benchmark_mode
        )
        system_prompt = f"{system_prompt}\n\nImportant: All assistant outputs must be in English."
        
        # Load prior messages from context if any
        messages = context.get('goal_oriented_messages', []) if context else []
        iterations = context.get('goal_oriented_iterations', []) if context else []
        step_trace: List[Dict] = []
        stop_reason = "max_iterations"
        
        selection_text = self._selection_brief((context or {}).get("pending_selection"))
        user_turn_text = (
            f"User query: {user_query}\n"
            f"{selection_text + chr(10) if selection_text else ''}"
            "Please continue analysis based on latest chart state and answer in English."
        )
        # Always append a new user turn so interrupted/new queries enter model context.
        messages.append({
            "role": "user",
            "content": [
                {"text": user_turn_text},
                {"image": f"data:image/png;base64,{image_base64}"},
            ],
        })
        
        current_spec = vega_spec
        current_image = image_base64
        current_state = None
        tool_registry_snapshot: List[Dict] = []
        try:
            registry = getattr(self.tool_executor, "registry", None)
            if registry is not None:
                tool_names = registry.list_tools_for_chart(chart_type)
                for name in tool_names:
                    info = registry.get_tool(name) or {}
                    tool_registry_snapshot.append(
                        {
                            "name": name,
                            "category": info.get("category", ""),
                            "description": info.get("description", ""),
                        }
                    )
        except Exception:
            tool_registry_snapshot = []
        agent_knowledge = AgentKnowledge(
            system_prompt=system_prompt,
            tool_registry=tool_registry_snapshot,
            chart_specific_usage=str(chart_type),
        )

        lower_query = str(user_query or "").lower()
        is_demo3_case = self._is_demo3_clarification_case(user_query, current_spec, context)
        if is_demo3_case and context is not None:
            context["demo3_case_active"] = True
        demo3_clarify_count = int((context or {}).get("demo3_clarify_count", 0))
        if is_demo3_case and demo3_clarify_count < 2:
            clarification_flows = [
                (
                    "Before I continue, which focus should we prioritize first?",
                    [
                        {"label": "Reduce incident risk first"},
                        {"label": "Find growth opportunity first"},
                        {"label": "Keep a balanced trade-off"},
                    ],
                ),
                (
                    "Got it. For the next step, should I focus on short-term spikes or long-term trend shifts?",
                    [
                        {"label": "Short-term spikes"},
                        {"label": "Long-term trend shifts"},
                        {"label": "Cover both quickly"},
                    ],
                ),
            ]
            question, options = clarification_flows[demo3_clarify_count]
            self._emit_guided_clarification(event_callback, question, options, iteration=1)
            if context is not None:
                context["demo3_clarify_count"] = demo3_clarify_count + 1
            if current_state is None and current_spec:
                current_state, _ = StateManager.split(current_spec)
            return {
                "success": True,
                "mode": "goal_oriented",
                "iterations": [],
                "step_trace": [],
                "stop_reason": "clarification_requested",
                "degraded_completion": False,
                "final_spec": current_spec,
                "final_state": current_state,
                "final_image": current_image,
                "_streamed_events": True,
            }

        need_guided_clarification = (
            ("not sure" in lower_query or "unsure" in lower_query or "where to start" in lower_query)
            and ("guide" in lower_query or "step by step" in lower_query or "pick a focus" in lower_query)
        ) or ("ask me to choose one path" in lower_query)
        if need_guided_clarification:
            self._emit_guided_clarification(
                event_callback,
                "Which direction should I prioritize first?",
                [
                    {"label": "Risk reduction"},
                    {"label": "Growth opportunity"},
                    {"label": "Balanced trade-off"},
                ],
                iteration=1,
            )
            if current_state is None and current_spec:
                current_state, _ = StateManager.split(current_spec)
            return {
                "success": True,
                "mode": "goal_oriented",
                "iterations": [],
                "step_trace": [],
                "stop_reason": "clarification_requested",
                "degraded_completion": False,
                "final_spec": current_spec,
                "final_state": current_state,
                "final_image": current_image,
                "_streamed_events": True,
            }

        loop = AgentLoop(Settings.MAX_GOAL_ORIENTED_ITERATIONS)

        def _run_iteration(iteration: int) -> bool:
            nonlocal current_spec, current_image, current_state, stop_reason
            emit_event(event_callback, AppEvents.ITERATION_STARTED, {"iteration": iteration + 1})
            # Log messages structure
            app_logger.info(f"iteration {iteration+1} - messages count: {len(messages)}")
            for idx, msg in enumerate(messages):
                role = msg['role']
                content_items = len(msg.get('content', []))
                has_image = any('image' in c for c in msg.get('content', []))
                app_logger.info(f"  msg {idx}: role={role}, items={content_items}, has_image={has_image}")
            
            # VLM call
            response = self.vlm.call(messages, system_prompt, expect_json=True)
            obs_state = current_state
            if obs_state is None:
                obs_state, _ = StateManager.split(current_spec)
            agent_observation = AgentObservation(
                user_query=user_query,
                widget_state=obs_state,
                rendered_view=current_image,
            )
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {"iteration": iteration + 1, "phase": "observe", "summary": "Read current chart state and query"},
            )
            # On VLM failure
            if not response.get("success"):
                app_logger.error(f"iteration {iteration+1} VLM failed: {response.get('error', 'Unknown')}")
                stop_reason = "vlm_error"
                # Record failed iteration
                iterations.append({
                    "iteration": iteration + 1,
                    "success": False,
                    "error": response.get('error', 'Unknown'),
                    "timestamp": time.time()
                })
                step_trace.append(
                    {
                        "iteration": iteration + 1,
                        "observe": {"error": response.get("error", "Unknown")},
                        "plan": {"stop_or_continue": "stop"},
                        "act": [],
                        "verify": [],
                        "reason": {"error": response.get("error", "Unknown")},
                        "observation_context": asdict(agent_observation),
                        "knowledge_context": asdict(agent_knowledge),
                        "tool_calls": [],
                        "state_updated": False,
                        "stop_signal": True,
                    }
                )
                emit_event(event_callback, AppEvents.ERROR, {"message": response.get("error", "Unknown")})
                emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
                return True
            
            # Append assistant message from VLM
            decision = response.get("parsed_json", {})
            goal_plan = self._goal_plan_snapshot(decision, user_query)
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {
                    "iteration": iteration + 1,
                    "phase": "plan",
                    "summary": self._goal_plan_summary(goal_plan),
                },
            )
            assistant_message = {
                "role": "assistant",
                "content": [{"text": response.get("content", "")}]  # raw VLM text
            }
            messages.append(assistant_message)
            
            # Trace logging
            tool_info = goal_plan.get("tool_name") or "None"
            achieved = goal_plan.get("goal_achieved", False)
            app_logger.info(f"iteration {iteration+1} VLM decision: tool={tool_info}, goal_achieved={achieved}")
            
            # Record iteration
            iteration_record = {
                "iteration": iteration + 1,
                "success": True,
                "timestamp": time.time(),
                "decision": decision,
                "vlm_raw_output": response.get("content", ""),  # raw VLM output
                "images": [current_image],
                "analysis_summary": {
                    "key_insights": decision.get("key_insights", []),
                    "reasoning": decision.get("reasoning", ""),
                    "answer": decision.get("answer", ""),
                }
            }
            step_record = {
                "iteration": iteration + 1,
                "observe": decision,
                "plan": {
                    "objective": goal_plan.get("objective", user_query),
                    "sub_goal": goal_plan.get("sub_goal", ""),
                    "goal_gap_note": goal_plan.get("goal_gap_note", ""),
                    "tool_name": goal_plan.get("tool_name"),
                    "tool_args": goal_plan.get("tool_args", {}),
                    "stop_or_continue": "stop" if goal_plan.get("goal_achieved", False) else "continue",
                },
                "act": [],
                "verify": [],
                "reason": {
                    "key_insights": decision.get("key_insights", []),
                    "reasoning": decision.get("reasoning", ""),
                    "final_response": decision.get("answer", ""),
                },
                "observation_context": asdict(agent_observation),
                "knowledge_context": asdict(agent_knowledge),
                "tool_calls": [],
                "state_updated": False,
                "stop_signal": False,
            }
            clarification = self._extract_clarification(decision)
            if clarification:
                stop_reason = "clarification_requested"
                step_record["stop_signal"] = True
                step_record["plan"]["stop_or_continue"] = "stop"
                iterations.append(iteration_record)
                step_trace.append(step_record)
                emit_event(
                    event_callback,
                    AppEvents.CLARIFICATION_REQUESTED,
                    {
                        "iteration": iteration + 1,
                        "question": clarification["question"],
                        "options": clarification["options"] or [],
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration + 1, "phase": "reason", "summary": "Clarification requested before next action"},
                )
                emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
                return True
            
            # Check goal achieved
            if goal_plan.get("goal_achieved", False):
                iterations.append(iteration_record)
                stop_reason = "goal_achieved"
                step_record["stop_signal"] = True
                step_record["act"].append(
                    {
                        "tool_name": "none",
                        "success": True,
                        "message": "No additional action required; objective already achieved in planning stage.",
                        "error": "",
                    }
                )
                step_record["verify"].append(
                    {
                        "iteration": iteration + 1,
                        "tool_name": "none",
                        "verify": {
                            "passed": True,
                            "mode": "goal_achieved_noop",
                            "message": "No action needed; objective already achieved.",
                        },
                    }
                )
                step_trace.append(step_record)
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration + 1, "phase": "act", "summary": "No action needed: objective already achieved"},
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration + 1, "phase": "verify", "summary": "No action to verify: objective already achieved"},
                )
                emit_event(
                    event_callback,
                    AppEvents.AGENT_MESSAGE,
                    {
                        "iteration": iteration + 1,
                        "objective": goal_plan.get("objective", user_query),
                        "sub_goal": goal_plan.get("sub_goal", ""),
                        "tool_name": goal_plan.get("tool_name"),
                        "goal_gap_note": goal_plan.get("goal_gap_note", ""),
                        "goal_achieved": True,
                        "final_response": decision.get("answer", ""),
                        "key_insights": decision.get("key_insights", []),
                        "reasoning": decision.get("reasoning", ""),
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration + 1, "phase": "reason", "summary": "Decided to stop: goal achieved"},
                )
                emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
                app_logger.info(f"Goal achieved at iteration {iteration + 1}")
                return True
            
            # Execute tools
            if goal_plan.get("tool_name"):
                tool_name = goal_plan["tool_name"]
                tool_params = goal_plan.get("tool_args", {})
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration + 1,
                        "phase": "act",
                        "summary": f"Calling tool: {tool_name}",
                    },
                )
                flow = execute_tool_and_update_view(
                    tool_executor=self.tool_executor,
                    vega_service=self.vega,
                    current_spec=current_spec,
                    current_image=current_image,
                    tool_name=tool_name,
                    tool_params=tool_params,
                    context=context,
                    apply_data_manager=self._apply_data_manager,
                )
                tool_result = flow["tool_result"]
                emit_event(
                    event_callback,
                    AppEvents.TOOL_STARTED,
                    {
                        "iteration": iteration + 1,
                        "tool_name": tool_name,
                        "tool_input": tool_params,
                    },
                )
                iteration_record["tool_execution"] = flow["tool_execution"]
                current_spec = flow["spec"]
                current_state = flow["state"]
                current_image = flow["image"]
                emit_event(
                    event_callback,
                    AppEvents.TOOL_FINISHED,
                    {
                        "iteration": iteration + 1,
                        "tool_name": tool_name,
                        "tool_result": tool_result,
                        "success": bool(tool_result.get("success", flow["status"] != "failed")),
                        "commit_immediately": flow["status"] == "analysis_only",
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration + 1,
                        "phase": "verify",
                        "summary": "Tool execution verified" if flow["status"] in ("state_updated", "analysis_only") else "Tool execution failed verification",
                    },
                )
                if flow["status"] == "state_updated":
                    step_record["state_updated"] = True
                    iteration_record["images"].append(current_image)
                    success_msg = flow["message"] or "Operation completed"
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": True,
                            "message": success_msg,
                            "error": "",
                        }
                    )
                    step_record["verify"].append(
                        {"iteration": iteration + 1, "tool_name": tool_name, "verify": {"passed": True, "mode": "state_updated", "message": success_msg}}
                    )
                    step_record["tool_calls"].append(iteration_record["tool_execution"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} succeeded.\n\nResult: {success_msg}\n\nHere is the updated view:"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    emit_event(
                        event_callback,
                        AppEvents.VIEW_UPDATED,
                        {
                            "iteration": iteration + 1,
                            "tool_name": tool_name,
                            "success": True,
                            "spec": current_spec,
                        },
                    )
                    app_logger.info(f"Re-rendered chart after {tool_name}: {success_msg}")
                elif flow["status"] == "analysis_only":
                    analysis_msg = flow["message"] or str(tool_result)
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": True,
                            "message": analysis_msg,
                            "error": "",
                        }
                    )
                    step_record["verify"].append(
                        {"iteration": iteration + 1, "tool_name": tool_name, "verify": {"passed": True, "mode": "analysis_only", "message": analysis_msg}}
                    )
                    step_record["tool_calls"].append(iteration_record["tool_execution"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} succeeded.\n\nAnalysis result: {analysis_msg}\n\nThe view did not change. Current view:"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    app_logger.info(f"Tool {tool_name} completed (analysis only): {analysis_msg}")
                elif flow["status"] == "render_failed":
                    iteration_record["success"] = False
                    render_error = flow["render_error"] or "Render failed"
                    stop_reason = "render_failed"
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": False,
                            "message": "",
                            "error": render_error,
                        }
                    )
                    step_record["verify"].append(
                        {"iteration": iteration + 1, "tool_name": tool_name, "verify": {"passed": False, "mode": "render_failed", "message": render_error}}
                    )
                    step_record["tool_calls"].append(iteration_record["tool_execution"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} caused a render failure: {render_error}\n\nCurrent view (unchanged):"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    app_logger.error(f"Failed to render after {tool_name}: {render_error}")
                else:
                    iteration_record["success"] = False
                    error_msg = tool_result.get("error", "Unknown error")
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": False,
                            "message": "",
                            "error": error_msg,
                        }
                    )
                    step_record["verify"].append(
                        {"iteration": iteration + 1, "tool_name": tool_name, "verify": {"passed": False, "mode": "tool_failed", "message": error_msg}}
                    )
                    step_record["tool_calls"].append(iteration_record["tool_execution"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} failed.\n\nError: {error_msg}\n\nPlease choose another available tool, or set goal_achieved: true if the goal is already achieved.\n\nCurrent view (unchanged):"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    app_logger.warning(f"Tool {tool_name} failed: {error_msg}")
            else:
                if not goal_plan.get("goal_achieved", False):
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "You did not propose a tool while the explicit goal is not achieved. "
                                    "Either propose one concrete goal-advancing action, request clarification, "
                                    "or set goal_achieved: true with a direct answer."
                                )
                            },
                            {"image": f"data:image/png;base64,{current_image}"},
                        ],
                    })
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration + 1,
                        "phase": "act",
                        "summary": "No tool call in this iteration",
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration + 1,
                        "phase": "verify",
                        "summary": "No action to verify",
                    },
                )
            
            if loop.is_final_iteration(iteration):
                step_record["stop_signal"] = True
                stop_reason = "max_iterations"
            iterations.append(iteration_record)
            step_trace.append(step_record)
            emit_event(
                event_callback,
                AppEvents.AGENT_MESSAGE,
                {
                    "iteration": iteration + 1,
                    "objective": goal_plan.get("objective", user_query),
                    "sub_goal": goal_plan.get("sub_goal", ""),
                    "tool_name": goal_plan.get("tool_name"),
                    "goal_gap_note": goal_plan.get("goal_gap_note", ""),
                    "goal_achieved": bool(goal_plan.get("goal_achieved", False)),
                    "final_response": decision.get("answer", ""),
                    "key_insights": decision.get("key_insights", []),
                    "reasoning": decision.get("reasoning", ""),
                },
            )
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {
                    "iteration": iteration + 1,
                    "phase": "reason",
                    "summary": "Assessed objective progress and next milestone",
                },
            )
            emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
            return False

        loop.run(_run_iteration)

        # Save messages and iterations to context for next turn
        if context is not None:
            context['goal_oriented_messages'] = messages
            context['goal_oriented_iterations'] = iterations
        
        if current_state is None and current_spec:
            current_state, _ = StateManager.split(current_spec)

        final_response = ""
        if iterations:
            last_decision = (iterations[-1].get("decision") or {}) if isinstance(iterations[-1], dict) else {}
            if isinstance(last_decision, dict):
                final_response = str(last_decision.get("answer", "") or "").strip()
                if not final_response:
                    insights = last_decision.get("key_insights") or []
                    if isinstance(insights, list) and insights:
                        final_response = str(insights[0]).strip()
                if not final_response:
                    final_response = str(last_decision.get("reasoning", "") or "").strip()

        return {
            "success": True,
            "mode": "goal_oriented",
            "iterations": iterations,
            "step_trace": step_trace,
            "stop_reason": stop_reason,
            "degraded_completion": stop_reason != "goal_achieved",
            "final_response": final_response,
            "final_spec": current_spec,
            "final_state": current_state,
            "final_image": current_image,
            "_streamed_events": True,
        }

    def _extract_region(self, spec: Dict) -> Dict:
        """Infer zoom region from spec (encoding.scale.domain)."""
        region = {}
        encoding = spec.get("encoding", {}) if isinstance(spec, dict) else {}
        x_enc = encoding.get("x", {}) if isinstance(encoding, dict) else {}
        y_enc = encoding.get("y", {}) if isinstance(encoding, dict) else {}

        def _parse_domain(dom):
            if isinstance(dom, list) and len(dom) == 2:
                try:
                    return float(dom[0]), float(dom[1])
                except Exception:  # noqa: BLE001
                    return None, None
            return None, None

        x_min, x_max = _parse_domain(x_enc.get("scale", {}).get("domain") if isinstance(x_enc.get("scale"), dict) else None)
        y_min, y_max = _parse_domain(y_enc.get("scale", {}).get("domain") if isinstance(y_enc.get("scale"), dict) else None)

        if x_min is not None or x_max is not None:
            region["x_min"] = x_min
            region["x_max"] = x_max
        if y_min is not None or y_max is not None:
            region["y_min"] = y_min
            region["y_max"] = y_max

        region["x_field"] = x_enc.get("field")
        region["y_field"] = y_enc.get("field")

        return region if any(v is not None for v in region.values()) else {}

    def _apply_data_manager(self, spec: Dict, context: Dict = None) -> Dict:
        """If session has data_manager, load region and return updated spec."""
        if not context:
            return spec

        data_manager = context.get("data_manager")
        session_id = context.get("session_id")
        if not data_manager or not session_id:
            return spec

        region = self._extract_region(spec)
        if not region:
            return spec

        try:
            current_count = get_spec_data_count(spec)
            new_values = data_manager.load_region(region)
            new_spec = copy.deepcopy(spec)
            new_spec.setdefault("data", {})["values"] = new_values
            app_logger.info(
                f"Region data loaded: {current_count} -> {len(new_values)} points "
                f"(region: x=[{region.get('x_min')}, {region.get('x_max')}], "
                f"y=[{region.get('y_min')}, {region.get('y_max')}])"
            )
            return new_spec
        except Exception as exc:  # noqa: BLE001
            app_logger.error(f"apply_data_manager failed: {exc}")
            return spec
