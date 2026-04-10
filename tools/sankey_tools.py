"""
（ Vega ）

（）：
- data  name="rawLinks"  ，: {source, target, value}
- data  name="nodeConfig" ，: {name, depth, order}
- data  name="depthLabelsData" ，: {depth, label}
-  Vega transform pipeline （stack + window + lookup），
-  signals ：threshold, selectedNode, nodeHover, edgeHover

 UI ：
    1.  spec ， get_node_options(spec) 。
    2.  _ui_hints （ get_node_options ），
        UI （ collapse/expand/filter ）。
    3. _ui_hints  adjacency  highlight_path ：
       ， adjacency[node].downstream 。
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import copy
import json
from state_manager import DataStore, StateManager, tool_output


def _ensure_state_has_data(state: Dict) -> Dict:
    data = state.get("data")
    if isinstance(data, list) and len(data) > 0:
        return state
    stored = DataStore.get()
    if isinstance(stored, list) and len(stored) > 0:
        return StateManager.reconstruct(copy.deepcopy(state), stored)
    return state


# ═══════════════════════════════════════════════════════════
#  
# ═══════════════════════════════════════════════════════════

def _parse_path_arg(path: Union[str, List[str]]) -> List[str]:
    """ path 。 JSON 。"""
    if isinstance(path, list):
        return [str(x).strip() for x in path if str(x).strip()]
    raw = (path or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.rstrip().endswith("]"):
        try:
            out = json.loads(raw)
            return [str(x).strip() for x in (out if isinstance(out, list) else [out]) if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def _escape_vega_str(name: str) -> str:
    """Vega （）。"""
    return str(name).replace("\\", "\\\\").replace("'", "\\'")


def _find_data_source(state: Dict, name: str) -> Tuple[Optional[List], Optional[int]]:
    """ Vega spec  data  name 。"""
    data = state.get("data", [])
    if not isinstance(data, list):
        store_data = DataStore.get()
        data = store_data if isinstance(store_data, list) else []
    if not isinstance(data, list):
        return None, None
    for i, d in enumerate(data):
        if isinstance(d, dict) and d.get("name") == name:
            return d.get("values", []), i
    return None, None


def _get_raw_links(state: Dict) -> Tuple[Optional[List[Dict]], Optional[int]]:
    return _find_data_source(state, "rawLinks")


def _get_node_config(state: Dict) -> Tuple[Optional[List[Dict]], Optional[int]]:
    return _find_data_source(state, "nodeConfig")


def _get_links(state: Dict) -> Tuple[Optional[List[Dict]], Optional[int]]:
    """csv_to_vega ：name='links', source/target """
    return _find_data_source(state, "links")


def _get_nodes(state: Dict) -> Tuple[Optional[List[Dict]], Optional[int]]:
    """csv_to_vega ：name='nodes', values=[{name: "A"}, ...]"""
    return _find_data_source(state, "nodes")


def _normalize_sankey_state(state: Dict) -> Dict:
    """
     spec  nodes/links（csv_to_vega ）， rawLinks  nodeConfig，
     rawLinks/nodeConfig 。 state，。
    """
    state = _ensure_state_has_data(state)
    links, _ = _find_data_source(state, "rawLinks")
    if links is not None:
        return state
    links_data, links_idx = _get_links(state)
    nodes_data, nodes_idx = _get_nodes(state)
    if not links_data or not nodes_data or links_idx is None or nodes_idx is None:
        return state
    #  -> 
    id_to_name = {}
    for i, n in enumerate(nodes_data):
        name = n.get("name", "")
        id_to_name[i] = name
    raw_links = []
    for link in links_data:
        src = link.get("source", 0)
        tgt = link.get("target", 0)
        val = float(link.get("value", 0))
        raw_links.append({
            "source": id_to_name.get(src, str(src)),
            "target": id_to_name.get(tgt, str(tgt)),
            "value": val
        })
    node_config = [
        {"name": n.get("name", ""), "depth": 0, "order": i}
        for i, n in enumerate(nodes_data)
    ]
    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)
    data = new_state.get("data", [])
    if not isinstance(data, list):
        return state
    new_state["data"] = list(data)
    new_state["data"].append({"name": "rawLinks", "values": raw_links})
    new_state["data"].append({"name": "nodeConfig", "values": node_config})
    return new_state


def _sync_sankey_state(state: Dict) -> Dict:
    """
     state  links/nodes  rawLinks/nodeConfig（ _normalize ），
     rawLinks/nodeConfig  links/nodes（rawLinks  source/target ）， rawLinks/nodeConfig。
    """
    raw_links, raw_links_idx = _get_raw_links(state)
    node_config, nc_idx = _get_node_config(state)
    links_data, links_idx = _get_links(state)
    nodes_data, nodes_idx = _get_nodes(state)
    if raw_links is None or node_config is None or links_data is None or nodes_data is None:
        return state
    name_to_idx = {n.get("name", ""): i for i, n in enumerate(node_config)}
    new_links = []
    for link in raw_links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        val = float(link.get("value", 0))
        new_links.append({
            "source": name_to_idx.get(src, 0),
            "target": name_to_idx.get(tgt, 0),
            "value": val
        })
    new_nodes = [{"name": n.get("name", "")} for n in node_config]
    new_state = copy.deepcopy(state)
    data = new_state.get("data", [])
    if not isinstance(data, list) or links_idx >= len(data) or nodes_idx >= len(data):
        return state
    new_state["data"][links_idx]["values"] = new_links
    new_state["data"][nodes_idx]["values"] = new_nodes
    new_state["data"] = [d for d in new_state["data"] if d.get("name") not in ("rawLinks", "nodeConfig")]
    return new_state


def _get_depth_labels(state: Dict) -> Tuple[Optional[List[Dict]], Optional[int]]:
    return _find_data_source(state, "depthLabelsData")


def _compute_node_flows(links: List[Dict]) -> Dict[str, Dict[str, float]]:
    """。"""
    flows: Dict[str, Dict[str, float]] = {}

    def _ensure(name: str):
        if name not in flows:
            flows[name] = {"inflow": 0.0, "outflow": 0.0, "total": 0.0}

    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        val = float(link.get("value", 0))
        _ensure(src)
        _ensure(tgt)
        flows[src]["outflow"] += val
        flows[tgt]["inflow"] += val

    for info in flows.values():
        info["total"] = max(info["inflow"], info["outflow"])

    return flows


def _find_signal(state: Dict, signal_name: str) -> Tuple[Optional[Dict], Optional[int]]:
    signals = state.get("signals", [])
    for i, sig in enumerate(signals):
        if isinstance(sig, dict) and sig.get("name") == signal_name:
            return sig, i
    return None, None


def _find_mark(state: Dict, mark_name: str) -> Optional[Dict]:
    for mark in state.get("marks", []):
        if mark.get("name") == mark_name:
            return mark
        if mark.get("type") == "group":
            for inner in mark.get("marks", []):
                if inner.get("name") == mark_name:
                    return inner
    return None


def _make_error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg}


def _make_success(operation: str, message: str, state: Dict = None, **extra) -> Dict[str, Any]:
    result = {"success": True, "operation": operation, "message": message}
    if state is not None:
        result["vega_state"] = _sync_sankey_state(state)
    result.update(extra)
    return result


def _ensure_working_data(spec: Dict[str, Any]) -> None:
    if isinstance(spec.get("data"), list):
        return
    store_data = DataStore.get()
    if isinstance(store_data, list):
        spec["data"] = copy.deepcopy(store_data)


def _build_ui_hints(state: Dict) -> Dict[str, Any]:
    """
     state  UI 。

    :
    {
        "all_nodes": ["Google Ads", "Facebook", ...],

        "nodes_by_depth": {
            "0": {
                "label": "Traffic Source",
                "nodes": [
                    {"name": "Google Ads", "order": 0, "total": 9000.0},
                    {"name": "Facebook",   "order": 1, "total": 7000.0},
                    ...
                ]
            },
            "1": { ... },
            ...
        },

        "depth_count": 5,
        "depth_labels": {"0": "Traffic Source", "1": "Entry Point", ...},

        "edges": [
            {"source": "Google Ads", "target": "Landing Page", "value": 5000},
            ...
        ],

        "adjacency": {
            "Google Ads": {
                "upstream": [],
                "downstream": ["Landing Page", "Product List"]
            },
            "Landing Page": {
                "upstream": ["Google Ads", "Facebook", "Organic"],
                "downstream": ["Product Detail", "Exit"]
            },
            ...
        },

        "collapsed_groups": {"Others (Layer 0)": ["Email", "Organic"], ...},

        "value_range": {"min": 1000, "max": 10000}
    }

    :
    ┌──────────────────────┬──────────────────────────────────────────────────────────┐
    │                   │  UI                                         │
    ├──────────────────────┼──────────────────────────────────────────────────────────┤
    │ highlight_path       │ nodes_by_depth ；adjacency.downstream   │
    │ trace_node           │ all_nodes                                    │
    │ collapse_nodes       │ nodes_by_depth                                   │
    │ expand_node          │ collapsed_groups  keys                          │
    │ calculate_conversion │ all_nodes （=）                    │
    │ color_flows          │ all_nodes                                        │
    │ reorder_nodes        │ nodes_by_depth                             │
    │ filter_flow          │ value_range  min/max                               │
    │ find_bottleneck      │ （）                                        │
    │ auto_collapse        │ （ top_n ）                              │
    └──────────────────────┴──────────────────────────────────────────────────────────┘
    """
    hints: Dict[str, Any] = {
        "all_nodes": [],
        "nodes_by_depth": {},
        "depth_count": 0,
        "depth_labels": {},
        "edges": [],
        "adjacency": {},
        "collapsed_groups": {},
        "value_range": {"min": 0, "max": 0}
    }

    nodes, _ = _get_node_config(state)
    links, _ = _get_raw_links(state)
    depth_labels_data, _ = _get_depth_labels(state)

    if not nodes or not links:
        return hints

    node_flows = _compute_node_flows(links)

    # depth labels
    label_map: Dict[int, str] = {}
    if depth_labels_data:
        for dl in depth_labels_data:
            label_map[dl.get("depth", -1)] = dl.get("label", "")

    # nodes_by_depth + all_nodes
    depth_groups: Dict[int, List[Dict]] = {}
    all_names: List[str] = []
    for node in sorted(nodes, key=lambda n: (n.get("depth", 0), n.get("order", 0))):
        name = node.get("name", "")
        depth = node.get("depth", 0)
        all_names.append(name)
        flow = node_flows.get(name, {})
        entry: Dict[str, Any] = {
            "name": name,
            "order": node.get("order", 0),
            "total": round(flow.get("total", 0), 2)
        }
        if node.get("_is_aggregate"):
            entry["is_aggregate"] = True
            entry["collapsed_nodes"] = node.get("_collapsed_nodes", [])
        depth_groups.setdefault(depth, []).append(entry)

    hints["all_nodes"] = all_names
    hints["depth_count"] = len(depth_groups)
    #  key  JSON 
    hints["nodes_by_depth"] = {
        str(depth): {
            "label": label_map.get(depth, f"Layer {depth}"),
            "nodes": node_list
        }
        for depth, node_list in sorted(depth_groups.items())
    }
    hints["depth_labels"] = {str(k): v for k, v in label_map.items()}

    # edges + adjacency + value_range
    edge_list = []
    adjacency: Dict[str, Dict[str, List[str]]] = {
        name: {"upstream": [], "downstream": []} for name in all_names
    }
    values = []

    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        val = float(link.get("value", 0))
        edge_list.append({"source": src, "target": tgt, "value": val})
        values.append(val)
        if src in adjacency and tgt not in adjacency[src]["downstream"]:
            adjacency[src]["downstream"].append(tgt)
        if tgt in adjacency and src not in adjacency[tgt]["upstream"]:
            adjacency[tgt]["upstream"].append(src)

    hints["edges"] = edge_list
    hints["adjacency"] = adjacency
    if values:
        hints["value_range"] = {"min": round(min(values), 2), "max": round(max(values), 2)}

    # collapsed groups
    state = state.get("_sankey_state", {})
    hints["collapsed_groups"] = state.get("collapsed_groups", {})

    return hints


# ═══════════════════════════════════════════════════════════
#  （ UI）
# ═══════════════════════════════════════════════════════════

def get_node_options(state: Dict) -> Dict[str, Any]:
    """
     state ， UI 。

    ：
    -  sankey spec 
    -  spec （ _ui_hints）

    Args:
        state: Vega 

    Returns:
         all_nodes, nodes_by_depth, adjacency, edges, collapsed_groups, value_range 。
    """
    state = _normalize_sankey_state(state)
    nodes, _ = _get_node_config(state)
    if not nodes:
        return _make_error("Cannot find nodeConfig data source")

    hints = _build_ui_hints(state)

    return {
        "success": True,
        "operation": "get_node_options",
        "message": f"Extracted {len(hints['all_nodes'])} nodes across {hints['depth_count']} layers",
        **hints
    }


# ═══════════════════════════════════════════════════════════
#  
# ═══════════════════════════════════════════════════════════

def filter_flow(state: Dict, min_value: float) -> Dict[str, Any]:
    """
    ： value >= min_value 。

    Args:
        state: Vega 
        min_value:  
    """
    state = _normalize_sankey_state(state)
    links, links_idx = _get_raw_links(state)
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    if not any(link.get("value", 0) >= min_value for link in links):
        return _make_error(f"No links with value >= {min_value}")

    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)

    sig, sig_idx = _find_signal(new_state, "threshold")
    if sig is not None:
        sig["value"] = min_value
        bind = sig.get("bind", {})
        if isinstance(bind, dict) and bind.get("input") == "range":
            if min_value > bind.get("max", 0):
                bind["max"] = min_value * 1.5
        filtered_count = sum(1 for l in links if l.get("value", 0) >= min_value)
        result = _make_success(
            "filter_flow",
            f"Set threshold signal to {min_value}. {filtered_count}/{len(links)} links visible.",
            state=new_state
        )
        result["_ui_hints"] = _build_ui_hints(new_state)
        return result

    filtered_links = [l for l in links if l.get("value", 0) >= min_value]
    used_nodes = set()
    for link in filtered_links:
        used_nodes.add(link["source"])
        used_nodes.add(link["target"])
    new_state["data"][links_idx]["values"] = filtered_links
    nodes, nodes_idx = _get_node_config(new_state)
    if nodes is not None and nodes_idx is not None:
        new_state["data"][nodes_idx]["values"] = [
            n for n in nodes if n.get("name") in used_nodes
        ]
    result = _make_success(
        "filter_flow",
        f"Filtered to {len(filtered_links)} links with value >= {min_value}",
        state=new_state
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def collapse_nodes(
    state: Dict,
    nodes_to_collapse: List[str],
    aggregate_name: str = "Other"
) -> Dict[str, Any]:
    """
    ：。

    Args:
        state:          Vega 
        nodes_to_collapse:  
        aggregate_name:     （ "Other"）
    """
    state = _normalize_sankey_state(state)
    links, links_idx = _get_raw_links(state)
    nodes, nodes_idx = _get_node_config(state)
    if links is None or nodes is None:
        return _make_error("Cannot find rawLinks or nodeConfig data source")

    collapse_set = set(nodes_to_collapse)
    existing_names = {n.get("name") for n in nodes}
    missing = collapse_set - existing_names
    if missing:
        return _make_error(f"Nodes not found: {sorted(missing)}")

    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)

    if "_sankey_state" not in new_state:
        new_state["_sankey_state"] = {
            "original_nodes": copy.deepcopy(nodes),
            "original_links": copy.deepcopy(links),
            "collapsed_groups": {}
        }
    state = new_state["_sankey_state"]
    state.setdefault("collapsed_groups", {})
    state["collapsed_groups"][aggregate_name] = list(nodes_to_collapse)

    collapse_depth = 0
    max_order = 0
    for n in nodes:
        if n.get("name") in collapse_set:
            collapse_depth = n.get("depth", 0)
        if n.get("depth") == collapse_depth:
            max_order = max(max_order, n.get("order", 0))

    new_nodes = [n for n in nodes if n.get("name") not in collapse_set]
    new_nodes.append({
        "name": aggregate_name,
        "depth": collapse_depth,
        "order": max_order + 1,
        "_is_aggregate": True,
        "_collapsed_nodes": list(nodes_to_collapse)
    })

    link_agg: Dict[Tuple[str, str], float] = {}
    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        val = float(link.get("value", 0))
        new_src = aggregate_name if src in collapse_set else src
        new_tgt = aggregate_name if tgt in collapse_set else tgt
        if new_src == aggregate_name and new_tgt == aggregate_name:
            continue
        key = (new_src, new_tgt)
        link_agg[key] = link_agg.get(key, 0) + val

    new_links = [{"source": s, "target": t, "value": v} for (s, t), v in link_agg.items()]

    new_state["data"][nodes_idx]["values"] = new_nodes
    new_state["data"][links_idx]["values"] = new_links

    result = _make_success(
        "collapse_nodes",
        f'Collapsed {len(nodes_to_collapse)} nodes into "{aggregate_name}"',
        state=new_state
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def expand_node(state: Dict, aggregate_name: str) -> Dict[str, Any]:
    """
    ：。

    Args:
        state:       Vega 
        aggregate_name:  
    """
    state = _normalize_sankey_state(state)
    sankey_state = state.get("_sankey_state", {})
    collapsed_groups = sankey_state.get("collapsed_groups", {})

    if not sankey_state:
        return _make_error("No _sankey_state found. The chart has no collapsed nodes.")
    if aggregate_name not in collapsed_groups:
        available = list(collapsed_groups.keys())
        return _make_error(f'"{aggregate_name}" is not a collapsed group. Available: {available}')

    original_nodes = sankey_state.get("original_nodes")
    original_links = sankey_state.get("original_links")
    if not original_nodes or not original_links:
        return _make_error("Original data lost, cannot expand")

    links, links_idx = _get_raw_links(state)
    nodes, nodes_idx = _get_node_config(state)
    if links is None or nodes is None:
        return _make_error("Cannot find rawLinks or nodeConfig data source")

    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)
    collapsed_node_names = set(collapsed_groups[aggregate_name])

    new_nodes = [n for n in nodes if n.get("name") != aggregate_name]
    for orig_node in original_nodes:
        if orig_node.get("name") in collapsed_node_names:
            new_nodes.append(copy.deepcopy(orig_node))

    current_node_names = {n.get("name") for n in new_nodes}
    restored_links = []
    for orig_link in original_links:
        src = orig_link.get("source")
        tgt = orig_link.get("target")
        if src in current_node_names and tgt in current_node_names:
            restored_links.append(copy.deepcopy(orig_link))

    for link in links:
        src = link.get("source")
        tgt = link.get("target")
        if src == aggregate_name or tgt == aggregate_name:
            continue
        if src in collapsed_node_names or tgt in collapsed_node_names:
            continue
        exists = any(
            l.get("source") == src and l.get("target") == tgt
            for l in restored_links
        )
        if not exists:
            restored_links.append(copy.deepcopy(link))

    new_state["data"][nodes_idx]["values"] = new_nodes
    new_state["data"][links_idx]["values"] = restored_links
    if "_sankey_state" in new_state and "collapsed_groups" in new_state["_sankey_state"]:
        del new_state["_sankey_state"]["collapsed_groups"][aggregate_name]

    result = _make_success(
        "expand_node",
        f'Expanded "{aggregate_name}" back to {len(collapsed_node_names)} nodes',
        state=new_state
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def auto_collapse_by_rank(state: Dict, top_n: int = 5) -> Dict[str, Any]:
    """
    ： top N ， "Others (Layer X)"。

    Args:
        state: Vega 
        top_n:      top （ 5）
    """
    state = _normalize_sankey_state(state)
    links, links_idx = _get_raw_links(state)
    nodes, nodes_idx = _get_node_config(state)
    if links is None or nodes is None:
        return _make_error("Cannot find rawLinks or nodeConfig data source")

    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)

    if "_sankey_state" not in new_state:
        new_state["_sankey_state"] = {
            "original_nodes": copy.deepcopy(nodes),
            "original_links": copy.deepcopy(links),
            "collapsed_groups": {}
        }
    state = new_state["_sankey_state"]
    state.setdefault("collapsed_groups", {})

    node_flows = _compute_node_flows(links)

    depth_groups: Dict[int, List[Dict]] = {}
    for node in nodes:
        depth = node.get("depth", 0)
        depth_groups.setdefault(depth, []).append(node)

    nodes_to_keep: set = set()
    collapsed_by_layer: Dict[int, Dict] = {}
    node_to_aggregate: Dict[str, str] = {}

    for depth, group in depth_groups.items():
        sorted_group = sorted(
            group,
            key=lambda n: node_flows.get(n.get("name"), {}).get("total", 0),
            reverse=True
        )
        for node in sorted_group[:top_n]:
            nodes_to_keep.add(node.get("name"))

        collapsed_names = [n.get("name") for n in sorted_group[top_n:]]
        if collapsed_names:
            agg_name = f"Others (Layer {depth})"
            collapsed_by_layer[depth] = {
                "aggregate_name": agg_name,
                "collapsed_nodes": collapsed_names
            }
            state["collapsed_groups"][agg_name] = collapsed_names
            for name in collapsed_names:
                node_to_aggregate[name] = agg_name

    if not collapsed_by_layer:
        result = _make_success(
            "auto_collapse_by_rank",
            f"All layers have <= {top_n} nodes, nothing to collapse",
            state=new_state
        )
        result["_ui_hints"] = _build_ui_hints(new_state)
        return result

    new_nodes = [n for n in nodes if n.get("name") in nodes_to_keep]
    for depth, info in collapsed_by_layer.items():
        max_order = max(
            (n.get("order", 0) for n in depth_groups.get(depth, [])),
            default=0
        )
        new_nodes.append({
            "name": info["aggregate_name"],
            "depth": depth,
            "order": max_order + 1,
            "_is_aggregate": True,
            "_collapsed_nodes": info["collapsed_nodes"]
        })

    link_agg: Dict[Tuple[str, str], float] = {}
    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        val = float(link.get("value", 0))
        new_src = node_to_aggregate.get(src, src)
        new_tgt = node_to_aggregate.get(tgt, tgt)
        key = (new_src, new_tgt)
        link_agg[key] = link_agg.get(key, 0) + val

    new_links = [{"source": s, "target": t, "value": v} for (s, t), v in link_agg.items()]

    new_state["data"][nodes_idx]["values"] = new_nodes
    new_state["data"][links_idx]["values"] = new_links

    total_collapsed = sum(len(info["collapsed_nodes"]) for info in collapsed_by_layer.values())
    result = _make_success(
        "auto_collapse_by_rank",
        f"Kept top {top_n} per layer, collapsed {total_collapsed} nodes into {len(collapsed_by_layer)} groups",
        state=new_state,
        collapsed_groups={
            info["aggregate_name"]: info["collapsed_nodes"]
            for info in collapsed_by_layer.values()
        }
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def reorder_nodes_in_layer(
    state: Dict,
    depth: int,
    order: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    。

    Args:
        state: Vega 
        depth:     （0, 1, 2, ...）
        order:     ，。 sort_by 。
        sort_by:   ："value_desc", "value_asc", "name"
    """
    if order is None and sort_by is None:
        return _make_error('Must specify either "order" or "sort_by"')
    if order is not None and sort_by is not None:
        return _make_error('Cannot specify both "order" and "sort_by"')

    state = _normalize_sankey_state(state)
    links, _ = _get_raw_links(state)
    nodes, nodes_idx = _get_node_config(state)
    if nodes is None:
        return _make_error("Cannot find nodeConfig data source")
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    layer_nodes = [n for n in nodes if n.get("depth") == depth]
    if not layer_nodes:
        return _make_error(f"No nodes found at depth {depth}")

    if order is not None:
        order_map = {name: i for i, name in enumerate(order)}
        sorted_names = sorted(
            [n.get("name") for n in layer_nodes],
            key=lambda name: order_map.get(name, 999999)
        )
    else:
        sort_key = str(sort_by).lower().strip()
        node_flows = _compute_node_flows(links)
        if sort_key == "value_desc":
            sorted_names = sorted(
                [n.get("name") for n in layer_nodes],
                key=lambda name: node_flows.get(name, {}).get("total", 0),
                reverse=True
            )
        elif sort_key == "value_asc":
            sorted_names = sorted(
                [n.get("name") for n in layer_nodes],
                key=lambda name: node_flows.get(name, {}).get("total", 0)
            )
        elif sort_key == "name":
            sorted_names = sorted(n.get("name") for n in layer_nodes)
        else:
            return _make_error(f'Invalid sort_by: {sort_by}. Use "value_desc", "value_asc", or "name"')

    name_to_new_order = {name: i for i, name in enumerate(sorted_names)}

    new_state = copy.deepcopy(state)
    _ensure_working_data(new_state)
    for node in new_state["data"][nodes_idx]["values"]:
        if node.get("depth") == depth and node.get("name") in name_to_new_order:
            node["order"] = name_to_new_order[node["name"]]

    method = f"order: {order}" if order else f"sort_by: {sort_by}"
    result = _make_success(
        "reorder_nodes_in_layer",
        f"Reordered {len(sorted_names)} nodes at depth {depth} ({method})",
        state=new_state,
        reordered_nodes=sorted_names
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


# ═══════════════════════════════════════════════════════════
#  
# ═══════════════════════════════════════════════════════════

def highlight_path(state: Dict, path: Union[str, List[str]]) -> Dict[str, Any]:
    """
    ：，。

    Args:
        state: Vega 
        path:      。 ["A","B","C"]、'["A","B","C"]'、'A,B,C'
    """
    state = _normalize_sankey_state(state)
    path = _parse_path_arg(path)
    if not path or len(path) < 2:
        return _make_error("Path must contain at least 2 nodes")

    links, _ = _get_raw_links(state)
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    link_set = {(l.get("source"), l.get("target")) for l in links}
    highlight_edges = []
    missing_edges = []
    for i in range(len(path) - 1):
        edge = (path[i], path[i + 1])
        if edge in link_set:
            highlight_edges.append(edge)
        else:
            missing_edges.append(f"{edge[0]} → {edge[1]}")

    if not highlight_edges:
        return _make_error(f"No valid edges in path. Missing: {missing_edges}")

    new_state = copy.deepcopy(state)

    path_nodes = set(path)
    edge_conditions = [
        f"(datum.source === '{_escape_vega_str(s)}' && datum.target === '{_escape_vega_str(t)}')"
        for s, t in highlight_edges
    ]
    is_on_path = " || ".join(edge_conditions)

    node_conditions = [f"datum.name === '{_escape_vega_str(n)}'" for n in path_nodes]
    is_path_node = " || ".join(node_conditions)

    edge_mark = _find_mark(new_state, "edgeMark")
    if edge_mark:
        update = edge_mark.setdefault("encode", {}).setdefault("update", {})
        update["fillOpacity"] = {"signal": f"({is_on_path}) ? 0.75 : 0.06"}
        update["strokeOpacity"] = {"signal": f"({is_on_path}) ? 0.5 : 0.02"}

    node_mark = _find_mark(new_state, "nodeRect")
    if node_mark:
        update = node_mark.setdefault("encode", {}).setdefault("update", {})
        update["fillOpacity"] = {"signal": f"({is_path_node}) ? 1.0 : 0.15"}
        update["strokeWidth"] = {"signal": f"({is_path_node}) ? 2.5 : 0.5"}

    path_desc = " → ".join(path)
    warning = f" (Note: edges not found: {missing_edges})" if missing_edges else ""
    result = _make_success(
        "highlight_path",
        f"Highlighted path: {path_desc}{warning}",
        state=new_state,
        highlighted_edges=len(highlight_edges),
        total_edges_in_path=len(path) - 1
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def trace_node(state: Dict, node_name: str) -> Dict[str, Any]:
    """
    ：。

    Args:
        state: Vega 
        node_name: 
    """
    state = _normalize_sankey_state(state)
    links, _ = _get_raw_links(state)
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    node_exists = any(
        l.get("source") == node_name or l.get("target") == node_name
        for l in links
    )
    if not node_exists:
        return _make_error(f'Node "{node_name}" not found in links')

    new_state = copy.deepcopy(state)

    sig, sig_idx = _find_signal(new_state, "selectedNode")
    if sig is not None:
        sig["value"] = node_name
        result = _make_success(
            "trace_node",
            f"Set selectedNode signal to '{node_name}'. Connected flows highlighted.",
            state=new_state
        )
        result["_ui_hints"] = _build_ui_hints(new_state)
        return result

    en = _escape_vega_str(node_name)
    edge_expr = f"datum.source === '{en}' || datum.target === '{en}' ? 0.75 : 0.08"
    node_expr = f"datum.name === '{en}' ? 1.0 : 0.2"

    edge_mark = _find_mark(new_state, "edgeMark")
    if edge_mark:
        update = edge_mark.setdefault("encode", {}).setdefault("update", {})
        update["fillOpacity"] = {"signal": edge_expr}

    node_mark = _find_mark(new_state, "nodeRect")
    if node_mark:
        update = node_mark.setdefault("encode", {}).setdefault("update", {})
        update["fillOpacity"] = {"signal": node_expr}

    result = _make_success(
        "trace_node",
        f"Traced all connections of node: {node_name}",
        state=new_state
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


def color_flows(state: Dict, nodes: List[str], color: str = "#e74c3c") -> Dict[str, Any]:
    """
    。

    Args:
        state: Vega 
        nodes:     
        color:     （ #e74c3c）
    """
    state = _normalize_sankey_state(state)
    links_data, _ = _get_raw_links(state)
    if links_data is None:
        return _make_error("Cannot find rawLinks data source")

    nodes_set = set(nodes or [])
    if not nodes_set:
        return _make_error("nodes list is empty")

    colored_edges = [
        (l.get("source"), l.get("target"))
        for l in links_data
        if l.get("source") in nodes_set or l.get("target") in nodes_set
    ]
    if not colored_edges:
        return _make_error(f"No flows connected to nodes: {sorted(nodes_set)}")

    new_state = copy.deepcopy(state)

    parts = [
        f"(datum.source === '{_escape_vega_str(s)}' && datum.target === '{_escape_vega_str(t)}')"
        for s, t in colored_edges
    ]
    is_colored = " || ".join(parts)

    edge_mark = _find_mark(new_state, "edgeMark")
    if edge_mark is None:
        return _make_error("Cannot find edgeMark in Vega spec")

    update_enc = edge_mark.get("encode", {}).get("update", {})
    original_fill = update_enc.get("fill", {})

    if isinstance(original_fill, dict) and "scale" in original_fill and "field" in original_fill:
        scale_name = original_fill["scale"]
        field_name = original_fill["field"]
        fallback = f"scale('{scale_name}', datum.{field_name})"
    elif isinstance(original_fill, dict) and "signal" in original_fill:
        fallback = f"({original_fill['signal']})"
    elif isinstance(original_fill, dict) and "value" in original_fill:
        fallback = f"'{original_fill['value']}'"
    else:
        fallback = "scale('color', datum.source)"

    fill_signal = f"({is_colored}) ? '{color}' : {fallback}"

    update = edge_mark.setdefault("encode", {}).setdefault("update", {})
    update["fill"] = {"signal": fill_signal}

    result = _make_success(
        "color_flows",
        f"Colored {len(colored_edges)} flows connected to nodes: {sorted(nodes_set)}",
        state=new_state,
        colored_count=len(colored_edges)
    )
    result["_ui_hints"] = _build_ui_hints(new_state)
    return result


# ═══════════════════════════════════════════════════════════
#  
# ═══════════════════════════════════════════════════════════

def calculate_conversion_rate(
    state: Dict,
    node_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    ：、。

    Args:
        state: Vega 
        node_name: （）。。
    """
    state = _normalize_sankey_state(state)
    links, _ = _get_raw_links(state)
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    node_flows = _compute_node_flows(links)
    ui_hints = _build_ui_hints(state)

    conversions = []
    for name in sorted(node_flows.keys()):
        info = node_flows[name]
        inflow = info["inflow"]
        outflow = info["outflow"]

        if inflow == 0 and outflow > 0:
            node_type = "source"
            rate = "source"
        elif outflow == 0 and inflow > 0:
            node_type = "sink"
            rate = 0.0
        else:
            node_type = "intermediate"
            rate = round(outflow / inflow, 4) if inflow > 0 else 0.0

        conversion: Dict[str, Any] = {
            "node": name,
            "inflow": round(inflow, 2),
            "outflow": round(outflow, 2),
            "rate": rate,
            "type": node_type
        }

        if node_type == "intermediate" and inflow > 0:
            loss = inflow - outflow
            conversion["loss"] = round(loss, 2)
            conversion["loss_rate"] = round(loss / inflow, 4)

        conversions.append(conversion)

    if node_name:
        target = [c for c in conversions if c["node"] == node_name]
        if not target:
            return _make_error(f'Node "{node_name}" not found')

        upstream = [
            {"from": l["source"], "value": l["value"]}
            for l in links if l.get("target") == node_name
        ]
        downstream = [
            {"to": l["target"], "value": l["value"]}
            for l in links if l.get("source") == node_name
        ]

        result = _make_success(
            "calculate_conversion_rate",
            f"Conversion analysis for {node_name}",
            node=node_name,
            conversion=target[0],
            upstream=upstream,
            downstream=downstream
        )
        result["_ui_hints"] = ui_hints
        return result

    sources = [c for c in conversions if c["type"] == "source"]
    sinks = [c for c in conversions if c["type"] == "sink"]
    intermediates = [c for c in conversions if c["type"] == "intermediate"]

    high_loss = sorted(
        [c for c in intermediates if c.get("loss_rate", 0) > 0],
        key=lambda x: x["loss_rate"],
        reverse=True
    )[:5]

    result = _make_success(
        "calculate_conversion_rate",
        f"Calculated conversion rates for {len(node_flows)} nodes",
        summary={
            "total_nodes": len(node_flows),
            "source_nodes": len(sources),
            "sink_nodes": len(sinks),
            "intermediate_nodes": len(intermediates)
        },
        conversions=conversions,
        high_loss_nodes=high_loss
    )
    result["_ui_hints"] = ui_hints
    return result


def find_bottleneck(state: Dict, top_n: int = 3) -> Dict[str, Any]:
    """
    。

    Args:
        state: Vega 
        top_n:      N 
    """
    state = _normalize_sankey_state(state)
    links, _ = _get_raw_links(state)
    if links is None:
        return _make_error("Cannot find rawLinks data source")

    node_flows = _compute_node_flows(links)

    bottlenecks = []
    for name, info in node_flows.items():
        inflow = info["inflow"]
        outflow = info["outflow"]
        if inflow > 0 and outflow > 0 and inflow > outflow:
            loss = inflow - outflow
            bottlenecks.append({
                "node": name,
                "inflow": round(inflow, 2),
                "outflow": round(outflow, 2),
                "loss": round(loss, 2),
                "loss_rate": round(loss / inflow, 4)
            })

    bottlenecks.sort(key=lambda x: x["loss_rate"], reverse=True)
    top = bottlenecks[:top_n]

    if not top:
        result = _make_success(
            "find_bottleneck",
            "No bottlenecks found (no intermediate nodes with loss)",
            bottlenecks=[],
            total_bottleneck_nodes=0
        )
        result["_ui_hints"] = _build_ui_hints(state)
        return result

    result = _make_success(
        "find_bottleneck",
        f"Found top {len(top)} bottleneck nodes with highest loss rates",
        bottlenecks=top,
        total_bottleneck_nodes=len(bottlenecks)
    )
    result["_ui_hints"] = _build_ui_hints(state)
    return result


# ═══════════════════════════════════════════════════════════
#  
# ═══════════════════════════════════════════════════════════

__all__ = [
    "get_node_options",
    "filter_flow",
    "highlight_path",
    "calculate_conversion_rate",
    "trace_node",
    "collapse_nodes",
    "expand_node",
    "auto_collapse_by_rank",
    "color_flows",
    "find_bottleneck",
    "reorder_nodes_in_layer",
]

for _fn_name in __all__:
    _fn = globals().get(_fn_name)
    if callable(_fn):
        globals()[_fn_name] = tool_output(_fn)