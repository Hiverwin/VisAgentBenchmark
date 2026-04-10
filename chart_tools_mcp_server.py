"""
chart tools MCP Server
wraps all visualization tools, called by Claude、GPT、Qwen etc.

usage:
    1. install dependencies: pip install mcp numpy scipy scikit-learn
    2. run stdio server: python chart_tools_mcp_server.py
    3. run remote HTTP server: python chart_tools_mcp_server.py --transport streamable-http --host 0.0.0.0 --port 8001
    4. or inspect locally: npx @modelcontextprotocol/inspector python chart_tools_mcp_server.py
"""

import argparse
from typing import Dict, List, Any, Tuple, Optional, Union
from mcp.server.fastmcp import FastMCP
from state_manager import StateManager, DataStore


# ============================================================
# initialize MCP Server
# ============================================================
mcp = FastMCP("chart_tools_mcp_server")


def _call(vega_spec: Dict, tool_func, **kwargs):
    """Split spec -> set DataStore -> call state-only tool -> return result."""
    state, data = StateManager.split(vega_spec)
    DataStore.set(data)
    return tool_func(state, **kwargs)


def _to_list(value: Optional[Union[Any, List[Any], Tuple[Any, ...]]]) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


# ==================== perception APIs ====================
@mcp.tool()
def get_data(vega_spec: Dict, scope: str = 'all') -> Dict[str, Any]:
    """Return raw data. scope: all | filter | visible | selected"""
    from tools import common
    return _call(vega_spec, common.get_data, scope=scope)


@mcp.tool()
def get_data_summary(vega_spec: Dict, scope: str = 'all') -> Dict[str, Any]:
    """Return data statistical summary. scope: visible or all"""
    from tools import common
    return _call(vega_spec, common.get_data_summary, scope=scope)


@mcp.tool()
def get_tooltip_data(vega_spec: Dict, position: Tuple[float, float]) -> Dict[str, Any]:
    """Get tooltip data at specified [x, y] position"""
    from tools import common
    return _call(vega_spec, common.get_tooltip_data, position=position)


@mcp.tool()
def get_view_spec(vega_spec: Dict) -> Dict[str, Any]:
    """Return structured view state: mark, encoding, domains, transforms, selections, etc."""
    from tools import common
    return _call(vega_spec, common.get_view_spec)


# ==================== bar chart tools ====================

@mcp.tool()
def sort_bars(vega_spec: Dict, order: str = "descending", by_subcategory: Optional[str] = None) -> Dict[str, Any]:
    """Sort bars. Stacked: use by_subcategory to sort x by that subcategory's value, or omit to sort stack layers by value. Grouped/simple: sort x by total."""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.sort_bars, order=order, by_subcategory=by_subcategory)

@mcp.tool()
def filter_categories(
    vega_spec: Dict,
    categories: Optional[List[str]] = None,
    category: Optional[Union[str, List[str]]] = None,
    values: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Remove specified x-axis categories. categories: list of values to REMOVE."""
    from tools import bar_chart_tools
    normalized = categories or _to_list(category) or _to_list(values)
    return _call(vega_spec, bar_chart_tools.filter_categories, categories=normalized)


@mcp.tool()
def highlight_top_n(
    vega_spec: Dict,
    n: int = 5,
    order: str = "descending",
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Highlight top N bars by aggregated value (supports stacked/grouped charts)"""
    from tools import bar_chart_tools
    # compat: category belongs to expand_stack, ignored here
    _ = category
    return _call(vega_spec, bar_chart_tools.highlight_top_n, n=n, order=order)


@mcp.tool()
def expand_stack(vega_spec: Dict, category: str) -> Dict[str, Any]:
    """Expand stacked bars in a category to parallel bars chart"""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.expand_stack, category=category)


@mcp.tool()
def toggle_stack_mode(vega_spec: Dict, mode: str = "grouped") -> Dict[str, Any]:
    """Toggle stacked/grouped display mode. mode: grouped or stacked"""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.toggle_stack_mode, mode=mode)


@mcp.tool()
def add_bars(vega_spec: Dict, values: List[Any], x_field: Optional[str] = None) -> Dict[str, Any]:
    """Add whole bars (x categories). Works for stacked or grouped bars."""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.add_bars, values=values, x_field=x_field)


@mcp.tool()
def remove_bars(vega_spec: Dict, values: List[Any], x_field: Optional[str] = None) -> Dict[str, Any]:
    """Remove whole bars (x categories) by hiding them via transform filter"""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.remove_bars, values=values, x_field=x_field)


@mcp.tool()
def filter_subcategories(
    vega_spec: Dict,
    subcategories_to_remove: List[Any],
    sub_field: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove specified subcategories (stack layers or grouped segments). subcategories_to_remove: values to REMOVE."""
    from tools import bar_chart_tools
    return _call(vega_spec, bar_chart_tools.filter_subcategories,
        subcategories_to_remove=subcategories_to_remove, sub_field=sub_field)


@mcp.tool()
def change_encoding(
    vega_spec: Dict,
    channel: str,
    field: str,
    type: Optional[str] = None,
    field_type: Optional[str] = None,
    encoding_type: Optional[str] = None,
    dtype: Optional[str] = None,
) -> Dict[str, Any]:
    """Modify encoding channel field mapping. Supports bar/line/heatmap/scatter Vega-Lite charts."""
    from tools import common
    if type is None:
        type = field_type or encoding_type or dtype
    return _call(vega_spec, common.change_encoding, channel=channel, field=field, type=type)


# ==================== Line chart tools ====================
@mcp.tool()
def zoom_x_region(vega_spec: Dict, start: str, end: str) -> Dict[str, Any]:
    """Zoom view to specific time range (does not delete data)"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.zoom_x_region, start=start, end=end)


@mcp.tool()
def highlight_trend(vega_spec: Dict, trend_type: str = "increasing") -> Dict[str, Any]:
    """Add regression trend line. trend_type: increasing or decreasing"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.highlight_trend, trend_type=trend_type)



@mcp.tool()
def detect_anomalies(vega_spec: Dict, threshold: float = 2.0) -> Dict[str, Any]:
    """Detect and highlight anomalies in the view (threshold in standard deviations)"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.detect_anomalies, threshold=threshold)


@mcp.tool()
def bold_lines(vega_spec: Dict, line_names: List[str], line_field: str = None) -> Dict[str, Any]:
    """Bold specified lines"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.bold_lines, line_names=line_names, line_field=line_field)


@mcp.tool()
def filter_lines(
    vega_spec: Dict,
    lines_to_remove: Optional[List[str]] = None,
    line_field: str = None,
    lines: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Remove specified lines. lines_to_remove: list of line names to REMOVE."""
    from tools import line_chart_tools
    normalized = lines_to_remove or lines or []
    return _call(vega_spec, line_chart_tools.filter_lines,
        lines_to_remove=normalized, line_field=line_field)


@mcp.tool()
def show_moving_average(vega_spec: Dict, window_size: int = 3) -> Dict[str, Any]:
    """Add moving average line"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.show_moving_average, window_size=window_size)


@mcp.tool()
def focus_lines(
    vega_spec: Dict,
    lines: Optional[List[str]] = None,
    line_field: Optional[str] = None,
    mode: str = "dim",
    dim_opacity: float = 0.08,
    line_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Focus on few lines, dim or hide others"""
    from tools import line_chart_tools
    normalized = lines or line_names or []
    return _call(vega_spec, line_chart_tools.focus_lines,
        lines=normalized, line_field=line_field, mode=mode, dim_opacity=dim_opacity)


@mcp.tool()
def resample_x_axis(
    vega_spec: Dict,
    granularity: str,
    agg: str = "mean",
) -> Dict[str, Any]:
    """Resample time series to different granularity (day/week/month/quarter/year)"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.resample_x_axis, granularity=granularity, agg=agg)


@mcp.tool()
def reset_resample_x_axis(vega_spec: Dict) -> Dict[str, Any]:
    """Reset time resampling to original granularity"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.reset_resample_x_axis)


@mcp.tool()
def drill_down_x_axis(
    vega_spec: Dict,
    level: str,
    value: Union[int, str],
    parent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Line chart time drilldown: year -> month -> date"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.drill_down_x_axis, level=level, value=value, parent=parent)


@mcp.tool()
def reset_drilldown_x_axis(vega_spec: Dict) -> Dict[str, Any]:
    """Reset line chart time drilldown to original state"""
    from tools import line_chart_tools
    return _call(vega_spec, line_chart_tools.reset_drilldown_x_axis)


# change_encoding is defined once above (bar section), delegates to common.change_encoding


# ==================== Scatter Plot Tools ====================
@mcp.tool()
def select_region(vega_spec: Dict, x_range: Tuple[float, float], y_range: Tuple[float, float]) -> Dict[str, Any]:
    """Select points in a specific region"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.select_region, x_range=x_range, y_range=y_range)


@mcp.tool()
def identify_clusters(vega_spec: Dict, n_clusters: int = 3, method: str = "kmeans") -> Dict[str, Any]:
    """Identify data clusters"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.identify_clusters, n_clusters=n_clusters, method=method)


@mcp.tool()
def calculate_correlation(vega_spec: Dict, method: str = "pearson") -> Dict[str, Any]:
    """Calculate correlation coefficient"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.calculate_correlation, method=method)


@mcp.tool()
def zoom_2d_region(vega_spec: Dict, x_range: Tuple[float, float], y_range: Tuple[float, float]) -> Dict[str, Any]:
    """Zoom to a rectangular region by filtering data and adjusting axis scales"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.zoom_2d_region, x_range=x_range, y_range=y_range)


@mcp.tool()
def filter_categorical(
    vega_spec: Dict,
    categories_to_remove: Optional[List[str]] = None,
    field: str = None,
    categories: Optional[List[str]] = None,
    column: Optional[str] = None,
) -> Dict[str, Any]:
    """Filter out data points of specified categories"""
    from tools import scatter_plot_tools
    normalized = categories_to_remove or categories or []
    field = field or column
    return _call(vega_spec, scatter_plot_tools.filter_categorical,
        categories_to_remove=normalized, field=field)


@mcp.tool()
def brush_region(vega_spec: Dict, x_range: Tuple[float, float], y_range: Tuple[float, float]) -> Dict[str, Any]:
    """Brush select a region, points outside become fainter"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.brush_region, x_range=x_range, y_range=y_range)


@mcp.tool()
def show_regression(vega_spec: Dict, method: str = "linear") -> Dict[str, Any]:
    """Add regression line (linear, log, exp, poly, quad)"""
    from tools import scatter_plot_tools
    return _call(vega_spec, scatter_plot_tools.show_regression, method=method)


# ==================== Heatmap Tools ====================
@mcp.tool()
def adjust_color_scale(vega_spec: Dict, scheme: str = "viridis", domain: List = None) -> Dict[str, Any]:
    """Adjust color scale (scheme and optional domain)"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.adjust_color_scale, scheme=scheme, domain=domain)


@mcp.tool()
def filter_cells(
    vega_spec: Dict,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Dict[str, Any]:
    """Keep only cells whose color value is in [min_value, max_value]. Omit one bound for one-sided range."""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.filter_cells, min_value=min_value, max_value=max_value)


@mcp.tool()
def highlight_region(
    vega_spec: Dict,
    x_values: Optional[List] = None,
    y_values: Optional[List] = None,
) -> Dict[str, Any]:
    """Highlight region by x_values and/or y_values"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.highlight_region, x_values=x_values, y_values=y_values)


@mcp.tool()
def highlight_region_by_value(
    vega_spec: Dict,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    outside_opacity: float = 0.12,
) -> Dict[str, Any]:
    """Highlight cells by value range (visual-only, dims outside range)"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.highlight_region_by_value,
        min_value=min_value, max_value=max_value, outside_opacity=outside_opacity)


@mcp.tool()
def filter_cells_by_region(
    vega_spec: Dict,
    x_value: Any = None,
    y_value: Any = None,
    x_values: Optional[List[Any]] = None,
    y_values: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Remove rows/columns. x_values/y_values: values to REMOVE."""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.filter_cells_by_region,
        x_value=x_value, y_value=y_value, x_values=x_values, y_values=y_values)


@mcp.tool()
def cluster_rows_cols(vega_spec: Dict, cluster_rows: bool = True,
                     cluster_cols: bool = True, method: str = "sum") -> Dict[str, Any]:
    """Reorder heatmap rows/cols by aggregate (sum/mean/max) of color field"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.cluster_rows_cols,
        cluster_rows=cluster_rows, cluster_cols=cluster_cols, method=method)


@mcp.tool()
def select_submatrix(vega_spec: Dict, x_values: List = None,
                    y_values: List = None) -> Dict[str, Any]:
    """Select submatrix by x_values and/or y_values"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.select_submatrix, x_values=x_values, y_values=y_values)


@mcp.tool()
def find_extremes(vega_spec: Dict, top_n: int = 5, mode: str = "both") -> Dict[str, Any]:
    """Find which cell(s) contain min/max value. Returns x and y axis labels of those cells. mode: max|min|both. top_n: number of extremes."""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.find_extremes, top_n=top_n, mode=mode)


@mcp.tool()
def threshold_mask(
    vega_spec: Dict,
    min_value: float,
    max_value: float,
    outside_opacity: float = 0.1,
) -> Dict[str, Any]:
    """Mask cells outside value range (visual-only, dims outside)"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.threshold_mask,
        min_value=min_value, max_value=max_value, outside_opacity=outside_opacity)


@mcp.tool()
def drilldown_axis(
    vega_spec: Dict,
    level: str,
    value: Union[int, str],
    parent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Heatmap time drilldown: year -> month -> date"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.drilldown_axis, level=level, value=value, parent=parent)


@mcp.tool()
def reset_drilldown(vega_spec: Dict) -> Dict[str, Any]:
    """Reset heatmap time drilldown to original state"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.reset_drilldown)


@mcp.tool()
def add_marginal_bars(
    vega_spec: Dict,
    op: str = "mean",
    show_top: bool = True,
    show_right: bool = True,
    bar_size: int = 70,
    bar_color: str = "#666666",
) -> Dict[str, Any]:
    """Add marginal bar charts (row/col aggregation) to heatmap"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.add_marginal_bars,
        op=op, show_top=show_top, show_right=show_right,
        bar_size=bar_size, bar_color=bar_color)


@mcp.tool()
def transpose(vega_spec: Dict) -> Dict[str, Any]:
    """Transpose heatmap: swap x and y axes"""
    from tools import heatmap_tools
    return _call(vega_spec, heatmap_tools.transpose)


# ==================== Sankey Tools ====================
@mcp.tool()
def filter_flow(vega_spec: Dict, min_value: float) -> Dict[str, Any]:
    """Filter flow: only show connections with value >= min_value"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.filter_flow, min_value=min_value)


@mcp.tool()
def highlight_path(vega_spec: Dict, path: List[str]) -> Dict[str, Any]:
    """Highlight multi-step path. path: node list e.g. [\"A\", \"B\", \"C\"]"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.highlight_path, path=path)


@mcp.tool()
def calculate_conversion_rate(vega_spec: Dict, node_name: Optional[str] = None) -> Dict[str, Any]:
    """Calculate conversion rate: analyze inflow, outflow, conversion rate per node"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.calculate_conversion_rate, node_name=node_name)


@mcp.tool()
def trace_node(vega_spec: Dict, node_name: str) -> Dict[str, Any]:
    """Trace node: highlight all connections connected to the node"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.trace_node, node_name=node_name)


@mcp.tool()
def collapse_nodes(
    vega_spec: Dict,
    nodes_to_collapse: Optional[List[str]] = None,
    aggregate_name: str = "Other",
    nodes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Collapse multiple nodes into a single aggregate node"""
    from tools import sankey_tools
    normalized = nodes_to_collapse or nodes or []
    return _call(vega_spec, sankey_tools.collapse_nodes,
        nodes_to_collapse=normalized, aggregate_name=aggregate_name)


@mcp.tool()
def expand_node(vega_spec: Dict, aggregate_name: str) -> Dict[str, Any]:
    """Expand aggregate node: restore collapsed original nodes"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.expand_node, aggregate_name=aggregate_name)


@mcp.tool()
def auto_collapse_by_rank(vega_spec: Dict, top_n: int = 5) -> Dict[str, Any]:
    """Auto collapse: keep top N nodes per layer, collapse others to Others (Layer X)"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.auto_collapse_by_rank, top_n=top_n)


@mcp.tool()
def color_flows(vega_spec: Dict, nodes: List[str], color: str = "#e74c3c") -> Dict[str, Any]:
    """Color flows connected to specified nodes"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.color_flows, nodes=nodes, color=color)


@mcp.tool()
def find_bottleneck(vega_spec: Dict, top_n: int = 3) -> Dict[str, Any]:
    """Identify nodes with the most severe loss"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.find_bottleneck, top_n=top_n)


@mcp.tool()
def reorder_nodes_in_layer(
    vega_spec: Dict,
    depth: int,
    order: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Reorder nodes in a layer. Provide order (list) or sort_by (value_desc|value_asc|name)"""
    from tools import sankey_tools
    return _call(vega_spec, sankey_tools.reorder_nodes_in_layer,
        depth=depth, order=order, sort_by=sort_by)


# ==================== Parallel coordinates tools ====================
@mcp.tool()
def reorder_dimensions(vega_spec: Dict, dimension_order: List[str]) -> Dict[str, Any]:
    """Reorder dimensions (supports fold-based and pre-normalized long format)"""
    from tools import parallel_coordinates_tools
    return _call(vega_spec, parallel_coordinates_tools.reorder_dimensions, dimension_order=dimension_order)


@mcp.tool()
def filter_by_category(
    vega_spec: Dict,
    field: Optional[str] = None,
    values: Optional[Union[str, List[str]]] = None,
    column: Optional[str] = None,
    dimension: Optional[str] = None,
    categories: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Remove data rows where field equals any of values. values: sample categories to REMOVE."""
    from tools import parallel_coordinates_tools
    field = field or column or dimension
    values = values if values is not None else categories
    return _call(vega_spec, parallel_coordinates_tools.filter_by_category, field=field, values=values)


@mcp.tool()
def highlight_category(
    vega_spec: Dict,
    field: Optional[str] = None,
    values: Optional[Union[str, List[str]]] = None,
    column: Optional[str] = None,
    dimension: Optional[str] = None,
    categories: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Highlight specified category, dim others"""
    from tools import parallel_coordinates_tools
    field = field or column or dimension
    values = values if values is not None else categories
    return _call(vega_spec, parallel_coordinates_tools.highlight_category, field=field, values=values)


@mcp.tool()
def hide_dimensions(
    vega_spec: Dict,
    dimensions: List[str],
    mode: str = "hide",
) -> Dict[str, Any]:
    """Hide/show dimensions in parallel coordinates (mode: hide|show)"""
    from tools import parallel_coordinates_tools
    return _call(vega_spec, parallel_coordinates_tools.hide_dimensions,
        dimensions=dimensions, mode=mode)


@mcp.tool()
def reset_hidden_dimensions(vega_spec: Dict) -> Dict[str, Any]:
    """Reset all hidden dimensions to visible"""
    from tools import parallel_coordinates_tools
    return _call(vega_spec, parallel_coordinates_tools.reset_hidden_dimensions)


# ============================================================
# ============================================================
# run server
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chart Tools MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default="stdio",
        help="MCP transport mode",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Reserved for future HTTP transport config")
    parser.add_argument("--port", type=int, default=8001, help="Reserved for future HTTP transport config")
    args = parser.parse_args()

    print(f" Starting Chart Tools MCP Server ({args.transport})...")
    if args.transport == "stdio":
        mcp.run()
    else:
        # FastMCP 2.x exposes streamable HTTP/SSE with library defaults.
        print(" HTTP transport uses FastMCP defaults (typically http://127.0.0.1:8000/mcp).")
        mcp.run(transport=args.transport)
