"""
Session manager: session state, intent routing, and mode dispatch.
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional
import uuid
import time

from config.chart_types import ChartType, get_candidate_chart_types
from config.intent_types import IntentType
from core.event_types import AppEvents, EventCallback, emit_event
from core.data_manager import LargeDatasetManager
from core.vlm_service import get_vlm_service
from core.vega_service import get_vega_service
from core.modes import ChitchatMode, GoalOrientedMode, AutonomousExplorationMode
from agent.runners import AppAgentRunner, AppRunnerDeps
from prompts import get_prompt_manager
from core.utils import app_logger, get_spec_data_count, get_spec_data_values, is_vega_full_spec
from tools import sankey_tools


class SessionManager:
    """session manager"""
    
    def __init__(self):
        self.sessions = {}  # session_id -> session_data
        self.vlm = get_vlm_service()
        self.vega = get_vega_service()
        self.prompt_mgr = get_prompt_manager()
        
        # initialize each mode
        self.chitchat_mode = ChitchatMode()
        self.goal_mode = GoalOrientedMode()
        self.explore_mode = AutonomousExplorationMode()
        self.app_runner = AppAgentRunner(
            AppRunnerDeps(
                run_chitchat=self.chitchat_mode.execute,
                run_goal=self.goal_mode.execute,
                run_explore=self.explore_mode.execute,
            )
        )
        
        app_logger.info("Session Manager initialized")

    @staticmethod
    def _spec_fingerprint(spec: Dict[str, Any]) -> str:
        try:
            return str(hash(json.dumps(spec, ensure_ascii=False, sort_keys=True, default=str)))
        except Exception:
            return str(hash(str(spec)))

    def _ensure_provenance_graph(self, session: Dict[str, Any]) -> Dict[str, Any]:
        graph = session.get("provenance_graph")
        if graph is None:
            graph = {
                "nodes": [],
                "edges": [],
                "baseline_node_id": None,
                "current_node_id": None,
                "branch_seq": 0,
                "pending_human_interrupt": None,
            }
            session["provenance_graph"] = graph
        graph.setdefault("nodes", [])
        graph.setdefault("edges", [])
        graph.setdefault("baseline_node_id", None)
        graph.setdefault("current_node_id", None)
        graph.setdefault("branch_seq", 0)
        graph.setdefault("pending_human_interrupt", None)
        return graph

    def _next_branch_id(self, graph: Dict[str, Any]) -> str:
        graph["branch_seq"] = int(graph.get("branch_seq", 0)) + 1
        return f"branch_{graph['branch_seq']}"

    def _append_provenance_edge(
        self,
        *,
        graph: Dict[str, Any],
        from_id: str,
        to_id: str,
        edge_type: str,
        semantic_type: str,
        created_by: str,
        iteration: Optional[int] = None,
        jump_type: Optional[str] = None,
        is_primary: bool = True,
        message_preview: str = "",
        branch_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        edge_id = f"edge_{len(graph.get('edges', [])) + 1}"
        graph.setdefault("edges", []).append(
            {
                "id": edge_id,
                "from_id": from_id,
                "to_id": to_id,
                "edge_type": edge_type,
                "semantic_type": semantic_type,
                "created_by": created_by,
                "iteration": iteration,
                "jump_type": jump_type or "none",
                "is_primary": bool(is_primary),
                "message_preview": (message_preview or "")[:200],
                "branch_id": branch_id,
                "meta": meta or {},
                "timestamp": time.time(),
            }
        )
        return edge_id

    @staticmethod
    def _find_latest_node_by_state_hash(graph: Dict[str, Any], state_hash: str) -> Optional[Dict[str, Any]]:
        if not state_hash:
            return None
        nodes = graph.get("nodes") or []
        for node in reversed(nodes):
            if node.get("state_hash") == state_hash:
                return node
        return None

    def _ensure_runtime_control(self, session: Dict[str, Any]) -> Dict[str, bool]:
        ctrl = session.get("control_state")
        if ctrl is None:
            ctrl = {
                "pause_requested": False,
                "resume_requested": False,
            }
            session["control_state"] = ctrl
        return ctrl

    def _append_provenance_node(
        self,
        *,
        session: Dict[str, Any],
        iteration: int,
        action_type: str,
        actor_type: str,
        tool_name: Optional[str],
        status: str,
        message_preview: str = "",
        edge_type: str = "agent_tool",
        target_node_id: Optional[str] = None,
        state_hash_override: Optional[str] = None,
    ) -> Optional[str]:
        graph = self._ensure_provenance_graph(session)
        current_spec = session.get("vega_spec") or {}
        state_hash = state_hash_override or self._spec_fingerprint(current_spec)
        node_id = f"node_{int(time.time() * 1000)}_{len(graph.get('nodes', [])) + 1}"
        parent = graph.get("current_node_id")
        parent_node = None
        if parent:
            parent_node = next((n for n in reversed(graph.get("nodes", [])) if n.get("id") == parent), None)

        edge_kind = "continue"
        semantic_type = "agent_continue"
        jump_type = "none"
        if edge_type in {"baseline"}:
            edge_kind = "baseline"
            semantic_type = "baseline"
        elif edge_type in {"branch", "human_interrupt", "human_interrupt_branch"}:
            edge_kind = "branch"
            semantic_type = "human_interrupt"
        elif edge_type in {"jump_back"}:
            edge_kind = "jump_back"
            semantic_type = "jump_back"
            jump_type = "jump_back"
        elif edge_type in {"reset"}:
            edge_kind = "jump_back"
            semantic_type = "reset"
            jump_type = "reset"
        elif edge_type in {"undo"}:
            edge_kind = "jump_back"
            semantic_type = "undo"
            jump_type = "undo"

        branch_id = parent_node.get("branch_id") if parent_node else "main"
        pending_interrupt = graph.get("pending_human_interrupt")
        if pending_interrupt and parent and pending_interrupt.get("from_id") == parent:
            edge_kind = "branch"
            semantic_type = "human_interrupt"
            jump_type = "none"
            branch_id = self._next_branch_id(graph)
            graph["pending_human_interrupt"] = None
        elif not branch_id:
            branch_id = "main"

        node = {
            "id": node_id,
            "iteration": iteration,
            "label": tool_name or action_type,
            "action_type": action_type,
            "actor_type": actor_type,
            "tool_name": tool_name,
            "status": status,
            "state_hash": state_hash,
            "message_preview": message_preview[:200] if message_preview else "",
            "timestamp": time.time(),
            "target_node_id": target_node_id,
            "parent_node_id": parent,
            "branch_id": branch_id,
        }
        graph.setdefault("nodes", []).append(node)

        if parent:
            self._append_provenance_edge(
                graph=graph,
                from_id=parent,
                to_id=node_id,
                edge_type=edge_kind,
                semantic_type=semantic_type,
                created_by=actor_type,
                iteration=iteration,
                jump_type=jump_type,
                is_primary=True,
                message_preview=message_preview,
                branch_id=branch_id,
            )
        graph["current_node_id"] = node_id
        return node_id

    def _apply_jump_back_relation(
        self,
        *,
        session: Dict[str, Any],
        iteration: int,
        source_node_id: str,
        target_node_id: str,
        jump_type: str,
        created_by: str = "system",
        message_preview: str = "",
    ) -> bool:
        graph = self._ensure_provenance_graph(session)
        if not source_node_id or not target_node_id:
            return False
        if source_node_id == target_node_id:
            return False
        self._append_provenance_edge(
            graph=graph,
            from_id=source_node_id,
            to_id=target_node_id,
            edge_type="jump_back",
            semantic_type=jump_type,
            created_by=created_by,
            iteration=iteration,
            jump_type=jump_type,
            is_primary=False,
            message_preview=message_preview,
            branch_id=None,
        )
        graph["current_node_id"] = target_node_id
        return True

    @staticmethod
    def _summarize_tool_result(tool_result: Dict[str, Any]) -> str:
        if not isinstance(tool_result, dict):
            return ""
        message = str(tool_result.get("message", "")).strip()
        if message:
            return message[:200]
        error = str(tool_result.get("error", "")).strip()
        if error:
            return error[:200]
        keys = [k for k in tool_result.keys() if k not in {"vega_spec", "state", "current_image", "images", "traceback"}]
        if not keys:
            return ""
        preview = "; ".join(f"{k}={tool_result.get(k)}" for k in keys[:3])
        return preview[:200]

    def _ingest_stream_event_for_provenance(
        self,
        *,
        session: Dict[str, Any],
        event_type: str,
        data: Dict[str, Any],
        stream_ctx: Dict[str, Any],
    ) -> None:
        if not isinstance(data, dict):
            return

        pending_tools = stream_ctx.setdefault("pending_tools", [])

        if event_type == AppEvents.TOOL_FINISHED:
            tool_name = str(data.get("tool_name") or "unknown_tool")
            iteration = data.get("iteration")
            if iteration is None:
                return
            tool_result = data.get("tool_result") if isinstance(data.get("tool_result"), dict) else {}
            if tool_name == "undo_view":
                edge_type = "undo"
                action_type = "undo"
                actor_type = "system"
            elif tool_name == "reset_view":
                edge_type = "reset"
                action_type = "reset"
                actor_type = "system"
            else:
                edge_type = "agent_tool"
                action_type = "tool_call"
                actor_type = "agent"

            pending_item = {
                "iteration": int(iteration),
                "tool_name": tool_name,
                "status": "finished" if bool(data.get("success", True)) else "failed",
                "success": bool(data.get("success", True)),
                "action_type": action_type,
                "actor_type": actor_type,
                "edge_type": edge_type,
                "message_preview": self._summarize_tool_result(tool_result),
                "committed": False,
                "source_node_id": self._ensure_provenance_graph(session).get("current_node_id"),
                "timestamp": time.time(),
            }
            pending_tools.append(pending_item)

            # analysis-only tools have no view.updated; commit immediately to avoid delayed trajectory nodes.
            if bool(data.get("commit_immediately", False)):
                if pending_item.get("tool_name") in {"reset_view", "undo_view"} and pending_item.get("success", True):
                    pending_item["committed"] = True
                    return
                self._append_provenance_node(
                    session=session,
                    iteration=int(pending_item.get("iteration", 0)),
                    action_type=pending_item.get("action_type", "tool_call"),
                    actor_type=pending_item.get("actor_type", "agent"),
                    tool_name=pending_item.get("tool_name"),
                    status=pending_item.get("status", "finished"),
                    message_preview=pending_item.get("message_preview", ""),
                    edge_type="continue" if pending_item.get("edge_type") == "agent_tool" else pending_item.get("edge_type", "continue"),
                )
                pending_item["committed"] = True
            return

        if event_type == AppEvents.VIEW_UPDATED:
            spec = data.get("spec")
            tool_name = str(data.get("tool_name") or "")
            iteration = data.get("iteration")
            if spec and isinstance(spec, dict):
                # keep session state aligned with streamed view updates
                session["vega_spec"] = spec
                state_hash = self._spec_fingerprint(spec)
            else:
                state_hash = None

            if tool_name == "final":
                return

            if iteration is None or not tool_name:
                return

            matched = None
            for item in reversed(pending_tools):
                if item.get("committed"):
                    continue
                if item.get("iteration") == int(iteration) and item.get("tool_name") == tool_name:
                    matched = item
                    break

            if matched is None:
                # fallback for legacy emitters that produce view.updated without tool.finished
                self._append_provenance_node(
                    session=session,
                    iteration=int(iteration),
                    action_type="tool_call",
                    actor_type="agent",
                    tool_name=tool_name,
                    status="finished" if bool(data.get("success", True)) else "failed",
                    message_preview=f"{tool_name} updated view",
                    edge_type="agent_tool",
                    state_hash_override=state_hash,
                )
                return

            # reset/undo are jump-back provenance relations, not forward timeline nodes.
            if matched.get("tool_name") in {"reset_view", "undo_view"} and matched.get("success", True):
                graph = self._ensure_provenance_graph(session)
                target_node = self._find_latest_node_by_state_hash(graph, state_hash) if state_hash else None
                if matched.get("tool_name") == "reset_view" and not target_node:
                    baseline_id = graph.get("baseline_node_id")
                    if baseline_id:
                        target_node = next((n for n in graph.get("nodes", []) if n.get("id") == baseline_id), None)
                if target_node is not None:
                    self._apply_jump_back_relation(
                        session=session,
                        iteration=int(iteration),
                        source_node_id=matched.get("source_node_id") or graph.get("current_node_id"),
                        target_node_id=target_node.get("id"),
                        jump_type="reset" if matched.get("tool_name") == "reset_view" else "undo",
                        created_by=matched.get("actor_type", "system"),
                        message_preview=matched.get("message_preview", ""),
                    )
                    matched["committed"] = True
                    return

            self._append_provenance_node(
                session=session,
                iteration=int(iteration),
                action_type=matched.get("action_type", "tool_call"),
                actor_type=matched.get("actor_type", "agent"),
                tool_name=matched.get("tool_name"),
                status=matched.get("status", "finished"),
                message_preview=matched.get("message_preview", ""),
                edge_type="continue" if matched.get("edge_type") == "agent_tool" else matched.get("edge_type", "continue"),
                state_hash_override=state_hash,
            )
            matched["committed"] = True

    def _flush_pending_stream_provenance(
        self,
        *,
        session: Dict[str, Any],
        stream_ctx: Dict[str, Any],
    ) -> None:
        pending_tools = stream_ctx.get("pending_tools") or []
        # analysis-only tools (without view.updated) still need trajectory nodes
        for item in pending_tools:
            if item.get("committed"):
                continue
            # For successful reset/undo we expect a view.updated to resolve jump target.
            # If it never arrived, skip creating fake forward nodes.
            if item.get("tool_name") in {"reset_view", "undo_view"} and item.get("success", True):
                item["committed"] = True
                continue
            self._append_provenance_node(
                session=session,
                iteration=int(item.get("iteration", 0)),
                action_type=item.get("action_type", "tool_call"),
                actor_type=item.get("actor_type", "agent"),
                tool_name=item.get("tool_name"),
                status=item.get("status", "finished"),
                message_preview=item.get("message_preview", ""),
                edge_type="continue" if item.get("edge_type") == "agent_tool" else item.get("edge_type", "continue"),
            )
            item["committed"] = True
    
    def create_session(self, vega_spec: Dict) -> str:
        """
        create a new session
        
        Args:
            vega_spec: Vega-Lite JSON specification
        
        Returns:
            session_id: the id of the session
        """
        session_id = str(uuid.uuid4())
        working_spec = copy.deepcopy(vega_spec)

        # if there is a large dataset configuration, initialize the manager and do the first sampling
        original_count = get_spec_data_count(working_spec)
        data_manager = self._maybe_init_data_manager(working_spec)
        if data_manager:
            initial_values = data_manager.init_sample()
            working_spec.setdefault("data", {})["values"] = initial_values
            app_logger.info(
                f"large dataset detected: {original_count} points -> "
                f"sampled to {len(initial_values)} points (view_limit={data_manager.view_limit})"
            )
        else:
            app_logger.info(f"dataset size: {original_count} points (no sampling needed)")
        
        # Sankey diagram auto collapse: if it is a Vega format and the number of nodes is too many
        working_spec = self._maybe_auto_collapse_sankey(working_spec)
        
        # render the initial view
        render_result = self.vega.render(working_spec)
        
        if not render_result.get("success"):
            app_logger.error("Failed to render initial view")
            return None
        
        # identify the chart type
        chart_type = self._identify_chart_type(
            working_spec,
            render_result["image_base64"]
        )
        
        # create session data
        self.sessions[session_id] = {
            "session_id": session_id,
            "vega_spec": working_spec,
            "original_spec": working_spec,  # preserve original spec
            "current_image": render_result["image_base64"],
            "chart_type": chart_type,
            "case_id": None,
            "conversation_history": [],
            "created_at": time.time(),
            "last_activity": time.time(),
            "data_manager": data_manager,
            "base_dir": str(Path(__file__).resolve().parent.parent),
            "spec_history": [],
            "pending_selection": None,
            "control_state": {
                "pause_requested": False,
                "resume_requested": False,
            },
            "provenance_graph": {
                "nodes": [],
                "edges": [],
                "baseline_node_id": None,
                "current_node_id": None,
            },
        }
        # initialize baseline node for branch-aware trajectory.
        baseline_id = self._append_provenance_node(
            session=self.sessions[session_id],
            iteration=0,
            action_type="baseline",
            actor_type="system",
            tool_name="baseline",
            status="finished",
            message_preview="Session initialized",
            edge_type="baseline",
        )
        if baseline_id:
            self.sessions[session_id]["provenance_graph"]["baseline_node_id"] = baseline_id
        
        app_logger.info(f"Session created: {session_id}, chart_type: {chart_type}")
        return session_id

    def _maybe_init_data_manager(self, vega_spec: Dict) -> Optional[LargeDatasetManager]:
        """when the data amount is greater than the view limit or provided full_data_path, initialize the data manager."""
        # Vega format (such as Sankey diagram) does not apply data sampling
        if is_vega_full_spec(vega_spec):
            return None
        
        meta = vega_spec.get("_metadata") or {}
        view_limit = meta.get("view_limit", 500)
        full_data_path = meta.get("full_data_path")

        encoding = vega_spec.get("encoding", {})
        x_field = encoding.get("x", {}).get("field")
        y_field = encoding.get("y", {}).get("field")

        full_values = get_spec_data_values(vega_spec) or []

        # if provided full_data_path, load it first
        if full_data_path:
            try:
                base_dir = Path(__file__).resolve().parent.parent
                data_path = (base_dir / full_data_path).resolve()
                if data_path.exists():
                    loaded = json.loads(data_path.read_text(encoding="utf-8")).get("values", [])
                    if loaded:
                        full_values = loaded
                else:
                    app_logger.warning(f"full_data_path not found: {data_path}")
            except Exception as exc:  # noqa: BLE001
                app_logger.error(f"failed to load full_data_path {full_data_path}: {exc}")

        if not full_values:
            return None

        if len(full_values) <= int(view_limit or 500):
            # the data amount is not greater than the limit, do not enable the manager
            return None

        return LargeDatasetManager(
            full_values=full_values,
            x_field=x_field,
            y_field=y_field,
            view_limit=view_limit,
        )
    
    def _maybe_auto_collapse_sankey(self, vega_spec: Dict, nodes_per_layer: int = 5) -> Dict:
        """
        Sankey diagram auto collapse: if the number of nodes in each layer is greater than the threshold, auto collapse
        
        this is the implementation of the "physical interaction necessity" of the Sankey diagram:
        - similar to the automatic sampling of the scatter plot
        - initially only display the top N nodes in each layer
        - the user must expand the node to see the collapsed nodes
        
        Args:
            vega_spec: Vega specification
            nodes_per_layer: the number of nodes to keep in each layer (default 5)
        
        Returns:
            the vega_spec that may have been collapsed
        """
        # only process the Vega format (Sankey diagram)
        if not is_vega_full_spec(vega_spec):
            return vega_spec
        
        # check if there are nodes and links data (Sankey diagram feature)
        data = vega_spec.get("data", [])
        if not isinstance(data, list):
            return vega_spec
        
        nodes_data = None
        for d in data:
            if isinstance(d, dict) and d.get("name") == "nodes":
                nodes_data = d.get("values", [])
                break
        
        if not nodes_data:
            return vega_spec
        
        # count the number of nodes by layer
        depth_counts = {}
        for node in nodes_data:
            depth = node.get("depth", 0)
            depth_counts[depth] = depth_counts.get(depth, 0) + 1
        
        # check if collapse is needed (any layer exceeds the threshold)
        needs_collapse = any(count > nodes_per_layer for count in depth_counts.values())
        
        if not needs_collapse:
            app_logger.info(f"sankey: {len(nodes_data)} nodes, no auto-collapse needed")
            return vega_spec
        
        # call auto collapse
        result = sankey_tools.auto_collapse_by_rank(vega_spec, top_n=nodes_per_layer)
        
        if result.get("success"):
            collapsed_info = result.get("collapsed_groups", {})
            total_collapsed = sum(len(nodes) for nodes in collapsed_info.values())
            app_logger.info(
                f"large sankey auto-collapsed: {len(nodes_data)} nodes -> "
                f"kept top {nodes_per_layer} per layer, {total_collapsed} nodes collapsed into {len(collapsed_info)} groups"
            )
            return result["vega_spec"]
        else:
            app_logger.warning(f"Sankey auto-collapse failed: {result.get('error')}")
            return vega_spec
    
    def _identify_chart_type(self, vega_spec: Dict, image_base64: str) -> ChartType:
        """identify the chart type"""
        # Infer from Vega spec first
        candidates = get_candidate_chart_types(vega_spec)
        
        if len(candidates) == 1 and candidates[0] != ChartType.UNKNOWN:
            return candidates[0]
        
        # if cannot determine, use VLM visual recognition
        prompt = """Identify the chart type. Respond with JSON:
{
    "chart_type": "bar_chart|line_chart|scatter_plot|parallel_coordinates|heatmap|sankey_diagram",
    "confidence": 0.0-1.0,
    "reasoning": "Brief rationale"
}"""
        
        response = self.vlm.call_with_image(prompt, image_base64, expect_json=True)
        
        if response.get("success"):
            parsed = response.get("parsed_json", {})
            chart_type_str = parsed.get("chart_type", "unknown")
            
            # convert to ChartType enum
            for ct in ChartType:
                if ct.value == chart_type_str:
                    return ct
        
        return ChartType.UNKNOWN
    
    def process_query(
        self,
        session_id: str,
        user_query: str,
        benchmark_mode: bool = False,
        event_callback: EventCallback = None,
        selection: Optional[Dict[str, Any]] = None,
        run_mode: Optional[str] = None,
    ) -> Dict:
        """
        process the user query
        
        Args:
            session_id: the id of the session
            user_query: the user query text
            benchmark_mode: whether in benchmark evaluation mode
        
        Returns:
            the processing result
        """
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
        
        session = self.sessions[session_id]
        session["last_activity"] = time.time()
        
        # 1. intent recognition (allow run_mode override from web layer)
        intent = self._resolve_intent_from_run_mode(run_mode) or self._recognize_intent(
            user_query,
            session["current_image"],
            session["chart_type"],
        )
        effective_mode = (
            "goal_oriented"
            if intent == IntentType.EXPLICIT_ANALYSIS
            else "autonomous"
            if intent == IntentType.VAGUE_EXPLORATION
            else "chitchat"
        )
        emit_event(
            event_callback,
            AppEvents.INTENT_RECOGNIZED,
            {
                "intent": intent.value if isinstance(intent, IntentType) else str(intent),
                "intent_display": intent.value if isinstance(intent, IntentType) else str(intent),
                "effective_mode": effective_mode,
            },
        )
        emit_event(
            event_callback,
            AppEvents.MODE_DETECTED,
            {"mode": effective_mode},
        )
        ctrl = self._ensure_runtime_control(session)
        if ctrl.get("resume_requested"):
            emit_event(event_callback, AppEvents.RUN_RESUMED, {})
            ctrl["resume_requested"] = False

        if selection:
            session["pending_selection"] = selection
        
        # 2. dispatch to different modes based on the intent
        stream_ctx: Dict[str, Any] = {"pending_tools": []}

        def _mode_event_callback(event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
            payload = data or {}
            self._ingest_stream_event_for_provenance(
                session=session,
                event_type=event_type,
                data=payload,
                stream_ctx=stream_ctx,
            )
            emit_event(event_callback, event_type, payload)

        if intent == IntentType.CHITCHAT:
            result = self.app_runner.run_chitchat(
                user_query,
                session["current_image"],
                session,
                event_callback=_mode_event_callback,
            )
        elif intent == IntentType.EXPLICIT_ANALYSIS:
            result = self.app_runner.run_goal_oriented(
                user_query,
                session["vega_spec"],
                session["current_image"],
                session["chart_type"],
                session,
                benchmark_mode=benchmark_mode,
                event_callback=_mode_event_callback,
            )
        else:  # VAGUE_EXPLORATION
            result = self.app_runner.run_autonomous(
                user_query,
                session["vega_spec"],
                session["current_image"],
                session["chart_type"],
                session,
                event_callback=_mode_event_callback,
            )
        
        if result.get("success"):
            session["vega_spec"] = result.get("final_spec", session["vega_spec"])
            session["current_image"] = result.get("final_image", session["current_image"])
            session["spec_history"].append(copy.deepcopy(session["vega_spec"]))
            if not result.get("_streamed_events"):
                self._emit_step_trace_events(session, result, _mode_event_callback)
            self._flush_pending_stream_provenance(session=session, stream_ctx=stream_ctx)
            emit_event(
                event_callback,
                AppEvents.VIEW_UPDATED,
                {
                    "iteration": len(result.get("step_trace") or []),
                    "tool_name": "final",
                    "success": True,
                    "spec": session.get("vega_spec"),
                },
            )
        else:
            emit_event(
                event_callback,
                AppEvents.ERROR,
                {"message": result.get("error", "Unknown error")},
            )
        
        # 3. update the conversation history
        session["conversation_history"].append({
            "query": user_query,
            "intent": intent.value if isinstance(intent, IntentType) else str(intent),
            "selection": selection,
            "result": result,
            "timestamp": time.time()
        })
        # Selection is one-turn context and should be consumed after current query.
        session["pending_selection"] = None

        if ctrl.get("pause_requested"):
            emit_event(event_callback, AppEvents.RUN_PAUSED, {"reason": "pause_requested"})
            ctrl["pause_requested"] = False
        
        return result

    def _emit_step_trace_events(
        self,
        session: Dict[str, Any],
        result: Dict[str, Any],
        event_callback: EventCallback,
    ) -> None:
        step_trace = result.get("step_trace") or []
        for step in step_trace:
            iteration = step.get("iteration")
            if iteration is None:
                continue
            emit_event(event_callback, AppEvents.ITERATION_STARTED, {"iteration": iteration})
            emit_event(
                event_callback,
                AppEvents.ITERATION_PHASE,
                {"iteration": iteration, "phase": "observe", "summary": "Read current chart state and query"},
            )
            reason = step.get("reason") or {}
            key_insights = reason.get("key_insights") if isinstance(reason, dict) else None
            reasoning = reason.get("reasoning") if isinstance(reason, dict) else None
            final_response = reason.get("final_response") if isinstance(reason, dict) else None
            if key_insights or reasoning or final_response:
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration, "phase": "reason", "summary": "Generated reasoning"},
                )
                emit_event(
                    event_callback,
                    AppEvents.AGENT_MESSAGE,
                    {
                        "iteration": iteration,
                        "key_insights": key_insights or [],
                        "reasoning": reasoning or "",
                        "final_response": final_response or "",
                    },
                )

            for call in step.get("tool_calls") or []:
                tool_name = call.get("tool_name") or "unknown_tool"
                tool_input = call.get("tool_params") or {}
                tool_result = call.get("tool_result") or {}
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {"iteration": iteration, "phase": "act", "summary": f"Calling tool: {tool_name}"},
                )
                emit_event(
                    event_callback,
                    AppEvents.TOOL_STARTED,
                    {
                        "iteration": iteration,
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.TOOL_FINISHED,
                    {
                        "iteration": iteration,
                        "tool_name": tool_name,
                        "tool_result": tool_result,
                        "success": bool(tool_result.get("success", True)),
                    },
                )
                emit_event(
                    event_callback,
                    AppEvents.ITERATION_PHASE,
                    {
                        "iteration": iteration,
                        "phase": "verify",
                        "summary": "Tool execution verified" if bool(tool_result.get("success", True)) else "Tool execution failed verification",
                    },
                )
            emit_event(event_callback, AppEvents.ITERATION_FINISHED, {"iteration": iteration})

    def _resolve_intent_from_run_mode(self, run_mode: Optional[str]) -> Optional[IntentType]:
        if not run_mode:
            return None
        run_mode_lower = str(run_mode).lower().strip()
        if run_mode_lower in {"cooperative", "goal_oriented", "goal-oriented"}:
            return IntentType.EXPLICIT_ANALYSIS
        if run_mode_lower in {"autonomous", "copilot", "exploration", "autonomous_exploration"}:
            return IntentType.VAGUE_EXPLORATION
        return None

    def load_region(self, session_id: str, region: Dict, current_spec: Dict) -> Dict:
        """load incremental data based on the region, return the new vega_spec."""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}

        session = self.sessions[session_id]
        data_manager: Optional[LargeDatasetManager] = session.get("data_manager")
        if not data_manager:
            return {"success": False, "error": "No data manager for session"}

        new_values = data_manager.load_region(region)
        new_spec = copy.deepcopy(current_spec)
        new_spec.setdefault("data", {})["values"] = new_values

        return {"success": True, "vega_spec": new_spec}
    
    def _recognize_intent(self, user_query: str, image_base64: str, 
                         chart_type: ChartType) -> IntentType:
        """Identify the user intent."""
        # Fast path: keyword heuristics
        query_lower = user_query.lower().strip()

        greetings = [
            'hi', 'hello', 'hey', 'hola', 'good morning', 'good afternoon',
            'good evening', 'good night', 'morning', 'evening'
        ]

        polite_words = [
            'thanks', 'thank you', 'thx', 'bye', 'goodbye', 'see you'
        ]

        system_queries = [
            'what can you do', 'how to use', 'who are you', 'what are you',
            'help me use', 'how does this work'
        ]

        # explicit action keywords -> EXPLICIT_ANALYSIS
        explicit_actions = [
            'filter', 'select',
            'zoom', 'scale',
            'highlight', 'emphasize',
            'sort', 'order',
            'show', 'hide',
            'compare', 'contrast',
            'choose', 'pick',
            'adjust', 'modify',
            'focus',
            'only show',
            'remove', 'delete',
            'add',
            'change to',
            'set to'
        ]

        # autonomous exploration cues -> VAGUE_EXPLORATION
        autonomous_cues = [
            'autonomous', 'autonomously', 'copilot',
            'explore', 'exploration', 'open-ended', 'open ended',
            'proactive', 'proactively', 'discover patterns',
            'you lead', 'explore first', 'free exploration', 'open exploration',
            'you analyze first', 'look for anomalies first', 'find anomalies first'
        ]
        
        # check if it is a pure greeting or polite words (length less than 10 characters)
        if len(query_lower) < 10:
            for greeting in greetings:
                if greeting in query_lower:
                    app_logger.info(f"Quick intent recognition: CHITCHAT (greeting: {greeting})")
                    return IntentType.CHITCHAT
            
            for polite in polite_words:
                if polite in query_lower:
                    app_logger.info(f"Quick intent recognition: CHITCHAT (polite: {polite})")
                    return IntentType.CHITCHAT
        
        # check if it is a system query (even if it is a long sentence)
        for sys_query in system_queries:
            if sys_query in query_lower:
                app_logger.info(f"Quick intent recognition: CHITCHAT (system query: {sys_query})")
                return IntentType.CHITCHAT
        
        # autonomous cues should take precedence over explicit action words
        # (many exploratory queries still contain words like compare/filter).
        for cue in autonomous_cues:
            if cue in query_lower:
                app_logger.info(f"Quick intent recognition: VAGUE_EXPLORATION (cue: {cue})")
                return IntentType.VAGUE_EXPLORATION

        # check if it is an explicit action keyword
        for action in explicit_actions:
            if action in query_lower:
                app_logger.info(f"Quick intent recognition: EXPLICIT_ANALYSIS (action: {action})")
                return IntentType.EXPLICIT_ANALYSIS
        
        # use VLM to identify the intent
        intent_prompt = self.prompt_mgr.get_intent_recognition_prompt(
            user_query=user_query,
            chart_type=chart_type
        )
        
        response = self.vlm.call_with_image(
            intent_prompt, image_base64,
            expect_json=True
        )
        
        if response.get("success"):
            parsed = response.get("parsed_json", {})
            intent_str = parsed.get("intent_type", "unknown")
            
            app_logger.info(f"VLM intent recognition: {intent_str}")
            
            for it in IntentType:
                if it.value == intent_str:
                    return it
        
        return IntentType.UNKNOWN
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """get the session data"""
        return self.sessions.get(session_id)

    def get_session_state(self, session_id: str) -> Optional[Dict]:
        session = self.get_session(session_id)
        if not session:
            return None
        state = {
            "session_id": session_id,
            "chart_type": str(session.get("chart_type", "")),
            "case_id": session.get("case_id"),
            "current_spec": session.get("vega_spec"),
            "current_image": session.get("current_image"),
            "spec_history": session.get("spec_history", []),
            "conversation_history": session.get("conversation_history", []),
            "created_at": session.get("created_at"),
            "last_activity": session.get("last_activity"),
            "dataset_id": session.get("dataset_id"),
            "provenance_graph": session.get("provenance_graph"),
        }
        sampling_info = self._get_sampling_info(session)
        if sampling_info is not None:
            state["sampling_info"] = sampling_info
        return state

    def request_pause(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        ctrl = self._ensure_runtime_control(session)
        ctrl["pause_requested"] = True
        return True

    def request_resume(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        ctrl = self._ensure_runtime_control(session)
        ctrl["resume_requested"] = True
        return True

    def record_human_interrupt(
        self,
        session_id: str,
        reason: str = "interrupt",
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        graph = self._ensure_provenance_graph(session)
        current_node_id = graph.get("current_node_id")
        if not current_node_id:
            return False
        # No fake pause node/edge. Mark the split point and let the next forward node
        # consume this marker as a branch edge from current view state.
        graph["pending_human_interrupt"] = {
            "from_id": current_node_id,
            "reason": reason,
            "meta": meta or {},
            "timestamp": time.time(),
        }
        return True

    def _get_sampling_info(self, session: Optional[Dict]) -> Optional[Dict[str, Any]]:
        if not session:
            return None
        data_manager: Optional[LargeDatasetManager] = session.get("data_manager")
        if not data_manager:
            return None
        chart_type = session.get("chart_type")
        return {
            "active": True,
            "chart_type": chart_type.value if isinstance(chart_type, ChartType) else str(chart_type),
            "displayed": len(data_manager.displayed_ids),
            "total": len(data_manager.full_values),
            "max_per_view": data_manager.view_limit,
        }
    
    def reset_view(self, session_id: str) -> Dict:
        """reset the view to the original state"""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
        
        session = self.sessions[session_id]
        graph = self._ensure_provenance_graph(session)
        from_node_id = graph.get("current_node_id")
        baseline_id = graph.get("baseline_node_id")
        session["vega_spec"] = session["original_spec"]
        
        render_result = self.vega.render(session["vega_spec"])
        if render_result.get("success"):
            session["current_image"] = render_result["image_base64"]
            if from_node_id and baseline_id:
                self._apply_jump_back_relation(
                    session=session,
                    iteration=0,
                    source_node_id=from_node_id,
                    target_node_id=baseline_id,
                    jump_type="reset",
                    created_by="system",
                    message_preview="View reset to original state",
                )
        
        return {"success": True, "message": "View reset to original state"}


_session_manager = None

def get_session_manager() -> SessionManager:
    """get the session manager singleton"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
