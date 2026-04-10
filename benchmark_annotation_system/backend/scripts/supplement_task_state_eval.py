#!/usr/bin/env python3
"""
Supplement benchmark task files with missing state_eval fields
and add state_check_fields to each question's ground_truth.

Processes reasoning steps in iteration order.  For most state keys the
last tool wins (overwrite).  For *cumulative* keys like ``layers``,
values are merged so that all layer-producing tools are reflected.

Usage:
    python supplement_task_state_eval.py [task_root] [--dry-run] [-v] [--backup]
"""

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Tool -> (state_eval_key, state_check_field) mapping
# ---------------------------------------------------------------------------

TOOL_STATE_KEY = {
    "sort_bars":                "sorting",
    "toggle_stack_mode":        "mark_mode",
    "expand_stack":             "mark_mode",
    "highlight_top_n":          "opacity",
    "focus_lines":              "opacity",
    "bold_lines":               "opacity",
    "highlight_category":       "opacity",
    "highlight_region":         "opacity",
    "highlight_region_by_value":"opacity",
    "threshold_mask":           "opacity",
    "resample_x_axis":            "time_unit",
    "detect_anomalies":         "anomaly_markers",
    "identify_clusters":        "cluster_field",
    "add_marginal_bars":        "layers",
    "highlight_trend":          "layers",
    "show_regression":          "layers",
    "show_moving_average":      "layers",
    "adjust_color_scale":       "color_scale",
    "cluster_rows_cols":        "clustering_order",
    "reorder_dimensions":       "axis_order",
    "hide_dimensions":          "dimensions",
    "zoom_x_region":          "visible_domain",
    "zoom_2d_region":          "visible_domain",
    "select_region":            "visible_domain",
    "brush_region":             "visible_domain",
    "filter_categories":        "data_filtered",
    "filter_subcategories":     "data_filtered",
    "filter_lines":             "data_filtered",
    "filter_cells_by_region":   "data_filtered",
    "filter_by_category":       "data_filtered",
    "filter_categorical":       "data_filtered",
    "filter_flow":              "data_filtered",
    "remove_bars":              "data_filtered",
    "change_encoding":          "encoding",
    "transpose":                "transpose",
    "drill_down_x_axis":      "visible_domain",
    "collapse_nodes":           "node_visibility",
    "expand_node":              "node_visibility",
    "auto_collapse_by_rank":    "node_visibility",
    "reorder_nodes_in_layer":   "node_order",
    "select_submatrix":         "data_filtered",
    "zoom_time_range":          "visible_domain",
    "zoom_dense_area":          "visible_domain",
}

# Filter-like tools: build_state_value returns None; keep data_filtered from existing state_eval when present.
FILTER_TOOLS = (
    "filter_categories", "filter_subcategories", "filter_lines",
    "filter_cells_by_region", "filter_by_category",
    "filter_categorical", "filter_flow", "remove_bars",
    "select_submatrix",
)

# Read-only tools that don't change state
READ_ONLY_TOOLS = {
    "get_data", "get_data_summary", "get_view_spec", "get_tooltip_data",
    "calculate_correlation", "calculate_conversion_rate", "find_bottleneck",
    "get_node_options", "render_chart", "find_extremes",
    "reset_view", "undo_view",
    "trace_node", "highlight_path", "color_flows",
}

# State keys where multiple tools accumulate rather than overwrite.
CUMULATIVE_STATE_KEYS = {"layers"}


def merge_layers(existing: Dict, new: Dict) -> Dict:
    """Merge a new layer tool's contribution into the accumulated layers dict.

    Rules:
      - ``regression_line``: boolean OR (never reverts True -> False).
      - ``count``: each subsequent layer tool adds layers on top of the
        existing count.  If neither side has ``count``, it is omitted.
      - ``has_type``: keep the first value (the evaluator checks whether a
        mark type exists *anywhere* in the spec, so the earlier type will
        still pass).
    """
    merged = dict(existing)
    for k, v in new.items():
        if k == "regression_line":
            merged[k] = merged.get(k, False) or v
        elif k == "count":
            if "count" in merged:
                extra = max(v - 1, 1)
                merged[k] = merged[k] + extra
            else:
                merged[k] = v + 1
        elif k == "has_type":
            if k not in merged:
                merged[k] = v
        else:
            merged[k] = v

    if "count" not in new and "count" in merged:
        merged["count"] = merged["count"] + 1

    return merged


# ---------------------------------------------------------------------------
# Extract target params from tool_eval
# ---------------------------------------------------------------------------

def _get_tool_target(tool_name: str, tool_eval: Dict) -> Optional[Dict]:
    """
    Find the param_eval.target for a specific tool from tool_eval.
    Returns the target value, or None if not found.
    """
    for t_info in tool_eval.get("tools", []):
        if t_info.get("tool") == tool_name:
            pe = t_info.get("param_eval", {})
            target = pe.get("target")
            param = pe.get("param", "")
            if pe.get("type") == "object" and param == "all_params":
                return target if isinstance(target, dict) else {}
            elif target is not None:
                return {param: target}
    return None


# ---------------------------------------------------------------------------
# Compute explicit sorted category list from spec data
# ---------------------------------------------------------------------------

def _compute_sort_list(vega_spec: Dict, order: str = "descending",
                       by_subcategory: Optional[str] = None) -> Optional[List]:
    """Replicate the sort_bars tool logic to produce the expected sorted
    category list.  Returns ``None`` on failure (missing data, etc.)."""
    enc = vega_spec.get("encoding", {})

    x_type = enc.get("x", {}).get("type", "nominal")
    y_type = enc.get("y", {}).get("type", "quantitative")

    if y_type in ("nominal", "ordinal") and x_type == "quantitative":
        cat_channel, val_channel = "y", "x"
    else:
        cat_channel, val_channel = "x", "y"

    cat_field = enc.get(cat_channel, {}).get("field")
    val_field = enc.get(val_channel, {}).get("field")
    color_field = enc.get("color", {}).get("field")
    val_agg = enc.get(val_channel, {}).get("aggregate", "mean")

    if not cat_field or not val_field:
        return None

    data_vals = vega_spec.get("data", {}).get("values")
    if not data_vals:
        return None

    try:
        df = pd.DataFrame(data_vals)
    except Exception:
        return None

    if cat_field not in df.columns or val_field not in df.columns:
        return None

    _AGG = {
        "mean": "mean", "sum": "sum", "count": "count",
        "median": "median", "min": "min", "max": "max",
    }
    agg_func = _AGG.get(val_agg, "mean")

    try:
        if by_subcategory and color_field and color_field in df.columns:
            sub = df[df[color_field].astype(str) == str(by_subcategory)]
            scores = sub.groupby(cat_field)[val_field].agg(agg_func)
        elif color_field and color_field in df.columns:
            per_group = df.groupby([cat_field, color_field])[val_field].agg(agg_func)
            scores = per_group.groupby(cat_field).sum()
        else:
            scores = df.groupby(cat_field)[val_field].agg(agg_func)
    except Exception:
        return None

    is_desc = order.lower() in ("descending", "desc")
    all_cats = df[cat_field].unique()
    sorted_cats = sorted(all_cats, key=lambda c: scores.get(c, 0), reverse=is_desc)
    return [x.item() if hasattr(x, "item") else x for x in sorted_cats]


def _load_spec_for_sort(vega_spec_path: str, project_root: Path) -> Optional[Dict]:
    """Load a Vega-Lite spec from *vega_spec_path* (may be relative to project root)."""
    p = Path(vega_spec_path)
    if not p.is_absolute():
        p = project_root / p
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Build state_eval value for each tool
# ---------------------------------------------------------------------------

def build_state_value(tool: str, target: Optional[Dict],
                      vega_spec_path: Optional[str] = None,
                      project_root: Optional[Path] = None) -> Optional[Dict]:
    """
    Build the state_eval value dict for a tool given its target params.
    Returns None if the tool doesn't map to a state field.
    """
    target = target or {}

    if tool == "sort_bars":
        order = target.get("order", "descending")
        by_sub = target.get("by_subcategory")
        sort_list: Optional[List] = None
        if vega_spec_path and project_root:
            spec = _load_spec_for_sort(vega_spec_path, project_root)
            if spec:
                sort_list = _compute_sort_list(spec, order=order,
                                               by_subcategory=by_sub)
        if sort_list is not None:
            return {"has_sort": True, "x_sort": sort_list}
        return {"has_sort": True}

    if tool == "toggle_stack_mode":
        mode = target.get("mode", "grouped")
        if mode == "grouped":
            return {"is_stacked": False}
        elif mode == "normalized":
            return {"is_stacked": True, "stacking": "normalize"}
        else:
            return {"is_stacked": True, "stacking": "zero"}

    if tool == "expand_stack":
        return {"is_stacked": False}

    if tool in ("highlight_top_n", "highlight_category",
                "highlight_region", "highlight_region_by_value",
                "threshold_mask"):
        return {"has_opacity": True, "has_condition": True}

    if tool in ("focus_lines", "bold_lines"):
        return {"has_opacity": True}

    if tool == "resample_x_axis":
        granularity = target.get("granularity", "month")
        return {"has_time_unit": True, "unit": granularity}

    if tool == "detect_anomalies":
        return {"has_markers": True, "marker_type": "point"}

    if tool == "identify_clusters":
        n = target.get("n_clusters", 3)
        return {"color_field_contains": "cluster"}

    if tool == "add_marginal_bars":
        show_top = target.get("show_top", True)
        show_right = target.get("show_right", True)
        count = 1 + (1 if show_top else 0) + (1 if show_right else 0)
        return {"count": count, "has_type": "bar"}

    if tool in ("highlight_trend", "show_regression"):
        return {"regression_line": True}

    if tool == "show_moving_average":
        return {"count": 2, "has_type": "line"}

    if tool == "adjust_color_scale":
        scheme = target.get("scheme")
        result = {}
        if scheme:
            result["scheme"] = scheme
        domain = target.get("domain")
        if domain:
            result["domain"] = domain
        return result if result else {}

    if tool == "cluster_rows_cols":
        return {"clustered": True}

    if tool == "reorder_dimensions":
        order = target.get("dimension_order")
        if order:
            return {"dimension_order": order}
        return {}

    if tool == "hide_dimensions":
        dims = target.get("dimensions", [])
        mode = target.get("mode", "hide")
        if mode == "hide":
            return {"hidden_fields": dims}
        else:
            return {"visible_fields": dims}

    if tool in ("zoom_x_region", "drill_down_x_axis"):
        start = target.get("start")
        end = target.get("end")
        result = {}
        if start is not None and end is not None:
            result["x"] = [start, end]
        return result

    if tool in ("zoom_2d_region", "select_region", "brush_region"):
        result = {}
        x_range = target.get("x_range")
        y_range = target.get("y_range")
        if x_range:
            result["x"] = x_range
        if y_range:
            result["y"] = y_range
        return result

    if tool == "zoom_time_range":
        start = target.get("start")
        end = target.get("end")
        result = {}
        if start is not None and end is not None:
            result["x"] = [start, end]
        return result if result else {}

    if tool == "zoom_dense_area":
        result = {}
        x_range = target.get("x_range")
        y_range = target.get("y_range")
        if x_range:
            result["x"] = x_range
        if y_range:
            result["y"] = y_range
        return result if result else {}

    if tool == "transpose":
        return {"transposed": True}

    if tool == "collapse_nodes":
        nodes = target.get("nodes_to_collapse", [])
        agg = target.get("aggregate_name", "")
        return {"hidden_nodes": nodes}

    if tool in ("expand_node",):
        return {}

    if tool == "auto_collapse_by_rank":
        return {}

    if tool == "reorder_nodes_in_layer":
        depth = target.get("depth")
        sort_by = target.get("sort_by")
        order = target.get("order")
        result = {}
        if order:
            result["order"] = order
        elif sort_by:
            result["sort_by"] = sort_by
        return result

    # filter tools: data_filtered
    if tool in ("filter_categories", "filter_subcategories", "filter_lines",
                "filter_cells_by_region", "filter_by_category",
                "filter_categorical", "filter_flow", "remove_bars",
                "select_submatrix"):
        # data_filtered is already handled by existing state_eval in most cases
        return None

    if tool == "change_encoding":
        return None

    return None


# ---------------------------------------------------------------------------
# Process one question
# ---------------------------------------------------------------------------

def process_question(question: Dict,
                     vega_spec_path: Optional[str] = None,
                     project_root: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """
    Rebuild state_eval and state_check_fields from reasoning + tool_eval.

    Starts from an empty state_eval so stale keys (e.g. encoding without
    change_encoding) are dropped. Preserves hand-authored fragments from the
    previous state_eval when the tool chain does not emit them (filters,
    change_encoding targets, parallel hide_dimensions aux transforms).
    """
    gt = question.get("ground_truth")
    if not gt:
        return False, []

    reasoning = gt.get("reasoning", [])
    tool_eval = gt.get("tool_eval", {})
    orig_state = copy.deepcopy(gt.get("state_eval", {}))

    original_state_eval = copy.deepcopy(orig_state)
    state_eval: Dict[str, Any] = {}
    changes: List[str] = []
    check_fields: set = set()

    sorted_steps = sorted(reasoning, key=lambda r: r.get("iteration", 0))
    reasoning_tools = [s.get("tool", "") for s in sorted_steps]

    cumulative_vals: Dict[str, Dict] = {}

    for step in sorted_steps:
        tool = step.get("tool", "")
        if not tool:
            continue

        if tool in READ_ONLY_TOOLS:
            continue

        state_key = TOOL_STATE_KEY.get(tool)
        if not state_key:
            continue

        target = _get_tool_target(tool, tool_eval)
        new_value = build_state_value(tool, target,
                                      vega_spec_path=vega_spec_path,
                                      project_root=project_root)

        if state_key in CUMULATIVE_STATE_KEYS and new_value is not None:
            if state_key in cumulative_vals:
                cumulative_vals[state_key] = merge_layers(
                    cumulative_vals[state_key], new_value)
            else:
                cumulative_vals[state_key] = dict(new_value)
            check_fields.add(state_key)
            continue

        if tool in FILTER_TOOLS and orig_state.get("data_filtered") is not None:
            state_eval["data_filtered"] = orig_state["data_filtered"]
            check_fields.add("data_filtered")
            continue

        if tool == "change_encoding" and orig_state.get("encoding") is not None:
            state_eval["encoding"] = orig_state["encoding"]
            check_fields.add("encoding")
            continue

        if tool == "adjust_color_scale" and (
                not new_value or new_value == {}) and orig_state.get("color_scale"):
            state_eval["color_scale"] = orig_state["color_scale"]
            check_fields.add("color_scale")
            continue

        if new_value is not None and new_value != {}:
            state_eval[state_key] = new_value
            check_fields.add(state_key)
        elif new_value == {} and state_key == "node_visibility" and orig_state.get("node_visibility"):
            state_eval["node_visibility"] = orig_state["node_visibility"]
            check_fields.add("node_visibility")

    for key, val in cumulative_vals.items():
        state_eval[key] = val

    if "hide_dimensions" in reasoning_tools:
        if orig_state.get("data_filtered") is not None and "data_filtered" not in state_eval:
            state_eval["data_filtered"] = orig_state["data_filtered"]
            check_fields.add("data_filtered")
        if orig_state.get("layers") is not None and "layers" not in state_eval:
            state_eval["layers"] = orig_state["layers"]
            check_fields.add("layers")

    new_check = sorted(k for k in check_fields if k in state_eval)

    for key in state_eval:
        if key not in original_state_eval:
            changes.append(f"add {key}")
        elif state_eval[key] != original_state_eval[key]:
            changes.append(f"overwrite {key}")

    for key in original_state_eval:
        if key not in state_eval:
            changes.append(f"remove {key}")

    old_check = gt.get("state_check_fields")
    if old_check != new_check:
        changes.append(f"set state_check_fields={new_check}")

    gt["state_eval"] = state_eval
    gt["state_check_fields"] = new_check

    return len(changes) > 0, changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Supplement task state_eval fields and add state_check_fields."
    )
    parser.add_argument(
        "task_root",
        nargs="?",
        default=None,
        help="Root dir of task files (default: synthetic_task/ relative to backend/)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--backup", action="store_true",
                        help="Create .bak backup before modifying each file")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    base = script_dir.parent.parent  # benchmark_annotation_system/
    project_root = base.parent       # workspace root
    task_root = Path(args.task_root) if args.task_root else base / "synthetic_task"

    if not task_root.is_dir():
        print(f"Error: not a directory: {task_root}", file=sys.stderr)
        sys.exit(1)

    all_files = []
    for root, dirs, fnames in os.walk(task_root):
        for f in sorted(fnames):
            if f.endswith(".json"):
                all_files.append(Path(root) / f)
    all_files.sort()

    files_changed = 0
    fields_added = 0
    total_questions = 0

    for fpath in all_files:
        try:
            text = fpath.read_text(encoding="utf-8")
            task = json.loads(text)
        except Exception as e:
            if args.verbose:
                print(f"  SKIP {fpath.name}: {e}")
            continue

        spec_path = task.get("vega_spec_path")
        file_changed = False
        for q in task.get("questions", []):
            total_questions += 1
            changed, change_list = process_question(
                q, vega_spec_path=spec_path, project_root=project_root)
            if changed:
                file_changed = True
                fields_added += len([c for c in change_list if c.startswith("add ")])
                if args.verbose:
                    rel = fpath.relative_to(task_root)
                    qid = q.get("qid", "?")
                    for c in change_list:
                        print(f"  {rel} [{qid}]: {c}")

        if file_changed:
            files_changed += 1
            if not args.dry_run:
                if args.backup:
                    bak = fpath.with_suffix(".json.bak")
                    if not bak.exists():
                        shutil.copy2(fpath, bak)
                out_text = json.dumps(task, indent=2, ensure_ascii=False) + "\n"
                fpath.write_text(out_text, encoding="utf-8")

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {files_changed} file(s), "
          f"added {fields_added} state_eval field(s), "
          f"across {total_questions} question(s) in {len(all_files)} file(s).")
    if args.dry_run:
        print("(dry-run: no files written)")


if __name__ == "__main__":
    main()
