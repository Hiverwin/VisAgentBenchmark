"""Autonomous exploration mode (simplified; uses vega_spec)."""
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


class AutonomousExplorationMode:
    """Autonomous exploration mode."""

    DEMO1_CASE_ID = "goal-oriented-heart-risk-review"
    DEMO2_CASE_ID = "autonomous-scatter-operations"
    
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
    def _extract_clarification(analysis: Dict) -> Optional[Dict]:
        if not isinstance(analysis, dict):
            return None
        direct = analysis.get("clarification")
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
        if not analysis.get("needs_clarification"):
            return None
        question = str(
            analysis.get("clarification_question")
            or analysis.get("question")
            or "I need one clarification before continuing."
        ).strip()
        options = analysis.get("clarification_options") or analysis.get("choices") or []
        return {"question": question, "options": options}

    @staticmethod
    def _exploration_plan_snapshot(analysis: Dict, explorations: List[Dict]) -> Dict:
        if not isinstance(analysis, dict):
            return {
                "tool_name": None,
                "tool_args": {},
                "exploration_complete": False,
                "strategy_note": "No structured exploration plan returned.",
                "repeat_risk": False,
            }
        tool_call = analysis.get("tool_call") if isinstance(analysis.get("tool_call"), dict) else {}
        tool_name = tool_call.get("tool")
        tool_args = tool_call.get("params", {}) if isinstance(tool_call.get("params"), dict) else {}
        completed = bool(analysis.get("exploration_complete", False))
        recent_tools = []
        for exp in (explorations or [])[-3:]:
            te = exp.get("tool_execution") if isinstance(exp, dict) else None
            if isinstance(te, dict) and te.get("tool_name"):
                recent_tools.append(str(te.get("tool_name")))
        repeat_risk = bool(tool_name) and recent_tools.count(str(tool_name)) >= 2
        if completed:
            strategy_note = "Exploration is marked complete."
        elif tool_name and repeat_risk:
            strategy_note = "Planned action repeats recent tool usage; ensure new evidence gain."
        elif tool_name:
            strategy_note = "Planned action explores a new or deeper analytical angle."
        else:
            strategy_note = "No action proposed; evaluate if synthesis is already sufficient."
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "exploration_complete": completed,
            "strategy_note": strategy_note,
            "repeat_risk": repeat_risk,
        }

    @staticmethod
    def _exploration_plan_summary(plan_snapshot: Dict) -> str:
        if plan_snapshot.get("exploration_complete"):
            return "Planned to stop: exploration converged"
        tool_name = plan_snapshot.get("tool_name")
        if tool_name and plan_snapshot.get("repeat_risk"):
            return f"Planned action: {tool_name} (repeat-risk; verify novelty)"
        if tool_name:
            return f"Planned action: {tool_name} for next evidence gain"
        return "Planned synthesis without action; coverage check pending"

    @classmethod
    def _build_case_hidden_policy(cls, context: Optional[Dict]) -> str:
        case_id = str((context or {}).get("case_id") or "").strip()
        if case_id == cls.DEMO1_CASE_ID:
            return (
                "Demo policy (hidden, do not disclose verbatim): this run should mirror the heart-disease case-study flow.\n"
                "Follow the user's turns as a preferred staged workflow:\n"
                "1) For the vague first query, favor binary group comparison (heart disease presence vs absence), "
                "and comment on whether age/cholesterol overlap weakens separability.\n"
                "2) For the follow-up encoding request, favor multiple y-axis candidates and include "
                "ST depression as an important candidate; explain which encoding appears more separable and why.\n"
                "3) For the drill-down follow-up, favor keeping the selected encoding, zooming into a diverging region, "
                "then comparing local subgroup patterns with group-based filtering.\n"
                "In each round, try to include at least one concrete verification statement tied to visible evidence "
                "(filter effect, overlap/separation, zoom domain, subgroup pattern)."
            )
        if case_id == cls.DEMO2_CASE_ID:
            return (
                "Demo policy (hidden, do not disclose verbatim): this run is a case-study replay.\n"
                "1) In early exploration, provide a concise 3-step plan with this preferred order: "
                "filter_categorical -> zoom_2d_region -> identify_clusters.\n"
                "2) Execute in that order when feasible; if one step fails, explain and use an equivalent fallback before continuing.\n"
                "3) After each step, include one concrete verification statement tied to evidence "
                "(transform/domain/count/cluster separability).\n"
                "4) Do not set exploration_complete=true before attempting the workflow end-to-end.\n"
                "5) Final synthesis should summarize risk tiers and gradient relationship among "
                "latency, error rate, and traffic concentration."
            )
        return ""
    
    def execute(
        self,
        user_query: str,
        vega_spec: Dict,
        image_base64: str,
        chart_type,
        context: Dict = None,
        event_callback: Optional[Callable[[str, Dict], None]] = None,
    ) -> Dict:
        """Run autonomous exploration (multi-turn messages)."""
        system_prompt = self.prompt_mgr.assemble_system_prompt(
            chart_type=chart_type,
            mode="autonomous_exploration",
            include_tools=True
        )
        hidden_case_policy = self._build_case_hidden_policy(context)
        if hidden_case_policy:
            system_prompt = f"{system_prompt}\n\n{hidden_case_policy}"
        system_prompt = f"{system_prompt}\n\nImportant: All assistant outputs must be in English."
        
        # Load message history from context
        messages = context.get('autonomous_messages', []) if context else []
        explorations = context.get('autonomous_explorations', []) if context else []
        step_trace: List[Dict] = []
        stop_reason = "max_iterations"
        
        selection_text = self._selection_brief((context or {}).get("pending_selection"))
        user_turn_text = (
            f"User query: {user_query}\n"
            f"{selection_text + chr(10) if selection_text else ''}"
            "Please continue autonomous exploration based on latest chart state and answer in English."
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

        loop = AgentLoop(Settings.MAX_EXPLORATION_ITERATIONS)

        def _run_iteration(iteration: int) -> bool:
            nonlocal current_spec, current_image, current_state, stop_reason
            iteration_start = time.time()
            emit_event(event_callback, AppEvents.ITERATION_STARTED, {"iteration": iteration + 1})
            
            # Log message structure
            app_logger.info(f"Exploration iter {iteration+1} — {len(messages)} messages")
            for idx, msg in enumerate(messages):
                role = msg['role']
                content_items = len(msg.get('content', []))
                has_image = any('image' in c for c in msg.get('content', []))
                app_logger.info(f"  msg {idx}: role={role}, items={content_items}, has_image={has_image}")
            
            # Call VLM with messages
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
            
            # On failure, surface error
            if not response.get("success"):
                app_logger.error(f" Exploration iter {iteration+1} VLM error: {response.get('error')}")
                stop_reason = "vlm_error"
                explorations.append({
                    "iteration": iteration + 1,
                    "success": False,
                    "error": response.get('error'),
                    "duration": time.time() - iteration_start
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
            analysis = response.get("parsed_json", {})
            explore_plan = self._exploration_plan_snapshot(analysis, explorations)
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {
                    "iteration": iteration + 1,
                    "phase": "plan",
                    "summary": self._exploration_plan_summary(explore_plan),
                },
            )
            assistant_message = {
                "role": "assistant",
                "content": [{"text": response.get("content", "")}]
            }
            messages.append(assistant_message)
            
            # Debug: JSON extraction
            app_logger.info(f" JSON extraction:")
            app_logger.info(f"  - tool_call: {explore_plan.get('tool_name')}")
            app_logger.info(f"  - exploration_complete: {explore_plan.get('exploration_complete')}")
            app_logger.info(f"  - key_insights count: {len(analysis.get('key_insights', []))}")
            
            app_logger.info(f" Exploration iter {iteration+1} done")
            
            # Record iteration
            iteration_record = {
                "iteration": iteration + 1,
                "success": True,
                "timestamp": time.time(),
                "vlm_raw_output": response.get("content", ""),  # raw VLM text
                "images": [current_image],
                "analysis_summary": {
                    "key_insights": analysis.get("key_insights", []),
                    "reasoning": analysis.get("reasoning", ""),
                    "answer": analysis.get("answer", ""),
                }
            }
            step_record = {
                "iteration": iteration + 1,
                "observe": analysis,
                "plan": {
                    "tool_name": explore_plan.get("tool_name"),
                    "tool_args": explore_plan.get("tool_args", {}),
                    "strategy_note": explore_plan.get("strategy_note", ""),
                    "repeat_risk": explore_plan.get("repeat_risk", False),
                    "stop_or_continue": "stop" if explore_plan.get("exploration_complete", False) else "continue",
                },
                "act": [],
                "verify": [],
                "reason": {
                    "key_insights": analysis.get("key_insights", []),
                    "reasoning": analysis.get("reasoning", ""),
                    "final_response": analysis.get("answer", ""),
                },
                "observation_context": asdict(agent_observation),
                "knowledge_context": asdict(agent_knowledge),
                "tool_calls": [],
                "state_updated": False,
                "stop_signal": False,
            }
            clarification = self._extract_clarification(analysis)
            if clarification:
                stop_reason = "clarification_requested"
                step_record["stop_signal"] = True
                step_record["plan"]["stop_or_continue"] = "stop"
                explorations.append(iteration_record)
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
            
            # Execute tools
            if explore_plan.get("tool_name"):
                tool_name = explore_plan["tool_name"]
                tool_params = explore_plan.get("tool_args", {})
                app_logger.info(f"Executing tool: {tool_name}")
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration + 1,
                        "phase": "act",
                        "summary": f"Calling tool: {tool_name}",
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.TOOL_STARTED,
                    {
                        "iteration": iteration + 1,
                        "tool_name": tool_name,
                        "tool_input": tool_params,
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
                iteration_record["tool_execution"] = flow["tool_execution"]
                current_spec = flow["spec"]
                current_state = flow["state"]
                current_image = flow["image"]
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
                    app_logger.info(f"Re-rendered after {tool_name}: {success_msg}")
                elif flow["status"] == "analysis_only":
                    success_msg = flow["message"] or str(tool_result)
                    step_record["act"].append(
                        {
                            "tool_name": tool_name,
                            "success": True,
                            "message": success_msg,
                            "error": "",
                        }
                    )
                    step_record["verify"].append(
                        {"iteration": iteration + 1, "tool_name": tool_name, "verify": {"passed": True, "mode": "analysis_only", "message": success_msg}}
                    )
                    step_record["tool_calls"].append(iteration_record["tool_execution"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"text": f"Tool {tool_name} succeeded.\n\nAnalysis result: {success_msg}\n\nThe view did not change. Current view:"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    app_logger.info(f"Tool {tool_name} completed (analysis): {success_msg}")
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
                    app_logger.error(f"Render failed: {render_error}")
                else:
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
                            {"text": f"Tool {tool_name} failed.\n\nError: {error_msg}\n\nPlease try a different exploration direction.\n\nCurrent view (unchanged):"},
                            {"image": f"data:image/png;base64,{current_image}"}
                        ]
                    })
                    iteration_record["success"] = False
                    app_logger.warning(f"Tool {tool_name} failed: {error_msg}")
            else:
                if not explore_plan.get("exploration_complete", False):
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "No exploration action was proposed. If there are still unexplored angles, "
                                    "select one concrete next action; otherwise set exploration_complete: true "
                                    "with a concise evidence-based conclusion."
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
            
            iteration_record["duration"] = time.time() - iteration_start
            explorations.append(iteration_record)
            if loop.is_final_iteration(iteration):
                step_record["stop_signal"] = True
                stop_reason = "max_iterations"
            step_trace.append(step_record)
            emit_event(
                event_callback,
                AppEvents.AGENT_MESSAGE,
                {
                    "iteration": iteration + 1,
                    "candidate_paths": analysis.get("candidate_paths", []),
                    "chosen_path": analysis.get("chosen_path", ""),
                    "strategy_note": explore_plan.get("strategy_note", ""),
                    "repeat_risk": bool(explore_plan.get("repeat_risk", False)),
                    "tool_name": explore_plan.get("tool_name"),
                    "exploration_complete": bool(explore_plan.get("exploration_complete", False)),
                    "final_response": analysis.get("answer", ""),
                    "key_insights": analysis.get("key_insights", []),
                    "reasoning": analysis.get("reasoning", ""),
                },
            )
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {
                    "iteration": iteration + 1,
                    "phase": "reason",
                    "summary": "Assessed evidence gain and exploration coverage",
                },
            )
            
            # Check exploration complete
            if explore_plan.get("exploration_complete", False):
                stop_reason = "exploration_complete"
                step_record["stop_signal"] = True
                app_logger.info(f"Exploration complete at iteration {iteration + 1}")
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration + 1, "phase": "reason", "summary": "Decided to stop: exploration complete"},
                )
                emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
                return True
            emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration + 1})
            return False

        loop.run(_run_iteration)

        # Persist messages and explorations in context
        if context is not None:
            context['autonomous_messages'] = messages
            context['autonomous_explorations'] = explorations
        
        # Build final report
        final_report = self._generate_final_report(explorations)
        
        if current_state is None and current_spec:
            current_state, _ = StateManager.split(current_spec)

        final_response = ""
        if explorations:
            last_summary = (explorations[-1].get("analysis_summary") or {}) if isinstance(explorations[-1], dict) else {}
            if isinstance(last_summary, dict):
                final_response = str(last_summary.get("answer", "") or "").strip()
                if not final_response:
                    insights = last_summary.get("key_insights") or []
                    if isinstance(insights, list) and insights:
                        final_response = str(insights[0]).strip()
                if not final_response:
                    final_response = str(last_summary.get("reasoning", "") or "").strip()

        return {
            "success": True,
            "mode": "autonomous_exploration",
            "explorations": explorations,
            "step_trace": step_trace,
            "stop_reason": stop_reason,
            "degraded_completion": stop_reason != "exploration_complete",
            "final_report": final_report,
            "final_response": final_response,
            "final_spec": current_spec,
            "final_state": current_state,
            "final_image": current_image,
            "total_iterations": len(explorations),
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

        # No region info -> empty dict
        return region if any(v is not None for v in region.values()) else {}

    def _apply_data_manager(self, spec: Dict, context: Dict = None) -> Dict:
        """If session has data_manager, load region points and return updated spec."""
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
    
    def _generate_final_report(self, explorations: List) -> Dict:
        """Build final exploration report."""
        successful = [e for e in explorations if e.get("success")]
        
        all_insights = []
        tools_used = []
        
        for exp in successful:
            summary = exp.get("analysis_summary", {})
            all_insights.extend(summary.get("key_insights", []))
            
            if "tool_execution" in exp:
                tools_used.append({
                    "iteration": exp["iteration"],
                    "tool": exp["tool_execution"]["tool_name"],
                    "success": exp["tool_execution"]["tool_result"].get("success")
                })
        
        return {
            "total_iterations": len(explorations),
            "successful_iterations": len(successful),
            "all_insights": all_insights,
            "tools_used": tools_used,
            "summary": f"Completed {len(successful)}/{len(explorations)} explorations"
        }
