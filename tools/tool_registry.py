"""
Tool registry (simplified — uses vega_spec instead of view_id).
"""

from typing import Dict, List, Callable, Any, Optional
from config.chart_types import ChartType
from state_manager import tool_output

from . import common
from . import bar_chart_tools
from . import line_chart_tools
from . import scatter_plot_tools
from . import parallel_coordinates_tools
from . import heatmap_tools
from . import sankey_tools


class ToolRegistry:
    """Registry of tool definitions."""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._chart_tools: Dict[ChartType, List[str]] = {}
        # plugin/custom tools are tracked separately for audit and easier export
        self._custom_tools: Dict[str, Dict[str, Any]] = {}
        self._custom_chart_tools: Dict[ChartType, List[str]] = {}
        self._register_all_tools()
    
    def _register_all_tools(self):
        """Register all built-in tools."""

        # Common tools (perception and basic actions)
        common_tools = {
            'get_view_spec': {
                'function': common.get_view_spec,
                'category': 'perception',
                'description': 'Return structured view state (encoding, domain, transforms, selections, etc.)',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'get_data': {
                'function': common.get_data,
                'category': 'perception',
                'description': 'Return a subset of raw data',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'scope': {'type': 'str', 'required': False, 'default': 'all', 'description': 'all | filter | visible | selected'}
                }
            },
            'get_data_summary': {
                'function': common.get_data_summary,
                'category': 'perception',
                'description': 'Get statistical summary of the data',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'scope': {'type': 'str', 'required': False, 'default': 'all'}
                }
            },
            'get_tooltip_data': {
                'function': common.get_tooltip_data,
                'category': 'perception',
                'description': 'Get tooltip data (hover)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'position': {'type': 'list', 'required': True, 'description': 'Data coordinates [x, y]'}
                }
            },
            'reset_view': {
                'function': common.reset_view,
                'category': 'action',
                'description': 'Reset view to original state (from vega_spec._original_spec metadata)',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'undo_view': {
                'function': common.undo_view,
                'category': 'action',
                'description': 'Undo last view change; restore previous version (from vega_spec._spec_history metadata)',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'render_chart': {
                'function': common.render_chart,
                'category': 'action',
                'description': 'Render the chart',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            }
        }
        
        # Bar chart tools
        bar_chart_tools_dict = {
            'sort_bars': {
                'function': bar_chart_tools.sort_bars,
                'category': 'action',
                'description': 'Sort bars by value. Stacked: pass by_subcategory to order the x-axis by that sub-series; omit to order stack layers by total subcategory value. Grouped/simple: order x-axis by total y.',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'order': {'type': 'str', 'required': False, 'default': 'descending', 'description': 'ascending or descending'},
                    'by_subcategory': {'type': 'str', 'required': False, 'description': 'Stacked charts: subcategory name (e.g. Diesel) to sort x by that series; omit to sort stack layer order'}
                }
            },
            'filter_categories': {
                'function': bar_chart_tools.filter_categories,
                'category': 'action',
                'description': 'Filter to specific categories',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'categories': {'type': 'list', 'required': True}
                }
            },
            'filter_subcategories': {
                'function': bar_chart_tools.filter_subcategories,
                'category': 'action',
                'description': 'Filter subcategories (color/xOffset encodings, e.g. stack layers or groups)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'subcategories_to_remove': {'type': 'list', 'required': True, 'description': 'Subcategory values to remove'},
                    'sub_field': {'type': 'str', 'required': False, 'description': 'Subcategory field name (optional, auto-detect)'}
                }
            },
            'highlight_top_n': {
                'function': bar_chart_tools.highlight_top_n,
                'category': 'action',
                'description': 'Highlight top N bars',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'n': {'type': 'int', 'required': False, 'default': 5},
                    'order': {'type': 'str', 'required': False, 'default': 'descending'}
                }
            },
            'expand_stack': {
                'function': bar_chart_tools.expand_stack,
                'category': 'action',
                'description': 'Expand one stacked category into side-by-side bars (helps compare layers that do not share a common baseline)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'category': {'type': 'str', 'required': True, 'description': 'X-axis category to expand (e.g. "East")'}
                }
            },
            'toggle_stack_mode': {
                'function': bar_chart_tools.toggle_stack_mode,
                'category': 'action',
                'description': 'Toggle stacked vs grouped display globally',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'mode': {'type': 'str', 'required': False, 'default': 'grouped', 'description': '"grouped" (side-by-side) or "stacked"'}
                }
            },
            'add_bars': {
                'function': bar_chart_tools.add_bars,
                'category': 'action',
                'description': 'Add whole bars by x category (stacked/grouped; can backfill from full_data_path)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'values': {'type': 'list', 'required': True, 'description': 'X category values to show, e.g. ["East"]'},
                    'x_field': {'type': 'str', 'required': False, 'description': 'X category field (optional, auto-detect)'}
                }
            },
            'remove_bars': {
                'function': bar_chart_tools.remove_bars,
                'category': 'action',
                'description': 'Remove whole bars by x category (stacked/grouped)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'values': {'type': 'list', 'required': True, 'description': 'X category values to hide, e.g. ["East"]'},
                    'x_field': {'type': 'str', 'required': False, 'description': 'X category field (optional, auto-detect)'}
                }
            },
            'add_bar_items': {
                'function': bar_chart_tools.add_bar_items,
                'category': 'action',
                'description': 'Add sub-bars by (x, sub-group); stacked=color layer, grouped=xOffset; can backfill from full_data_path',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'items': {'type': 'list', 'required': True, 'description': 'Items to add, e.g. [{"x":"East","sub":"Electronics"}]'},
                    'x_field': {'type': 'str', 'required': False, 'description': 'X field (optional, auto-detect)'},
                    'sub_field': {'type': 'str', 'required': False, 'description': 'Sub-group field (optional; prefers xOffset.field, then color.field)'}
                }
            },
            'remove_bar_items': {
                'function': bar_chart_tools.remove_bar_items,
                'category': 'action',
                'description': 'Remove sub-bars by (x, sub-group); stacked=color layer, grouped=xOffset',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'items': {'type': 'list', 'required': True, 'description': 'Items to hide, e.g. [{"x":"East","sub":"Electronics"}]'},
                    'x_field': {'type': 'str', 'required': False, 'description': 'X field (optional, auto-detect)'},
                    'sub_field': {'type': 'str', 'required': False, 'description': 'Sub-group field (optional; prefers xOffset.field, then color.field)'}
                }
            },
            'change_encoding': {
                'function': bar_chart_tools.change_encoding,
                'category': 'action',
                'description': 'Change field mapping for an encoding channel (color, size, shape, opacity, x, y, ...)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'channel': {'type': 'str', 'required': True, 'description': 'Encoding channel (color, size, shape, opacity, x, y, ...)'},
                    'field': {'type': 'str', 'required': True, 'description': 'New field name'},
                    'type': {'type': 'str', 'required': False, 'description': 'Optional type: quantitative | nominal | ordinal | temporal'}
                }
            }
        }
        
        # Line chart tools
        line_chart_tools_dict = {
            'zoom_x_region': {
                'function': line_chart_tools.zoom_x_region,
                'category': 'action',
                'description': 'Zoom the time range',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'start': {'type': 'str', 'required': True},
                    'end': {'type': 'str', 'required': True}
                }
            },
            'highlight_trend': {
                'function': line_chart_tools.highlight_trend,
                'category': 'action',
                'description': 'Highlight trend',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'trend_type': {'type': 'str', 'required': False, 'default': 'increasing'}
                }
            },
            'detect_anomalies': {
                'function': line_chart_tools.detect_anomalies,
                'category': 'analysis',
                'description': 'Detect anomaly points',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'threshold': {'type': 'float', 'required': False, 'default': 2.0}
                }
            },
            'bold_lines': {
                'function': line_chart_tools.bold_lines,
                'category': 'action',
                'description': 'Bold selected lines',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'line_names': {'type': 'list', 'required': True, 'description': 'Line series names to bold'},
                    'line_field': {'type': 'str', 'required': False, 'description': 'Line grouping field (optional, auto-detect)'}
                }
            },
            'filter_lines': {
                'function': line_chart_tools.filter_lines,
                'category': 'action',
                'description': 'Remove specified lines',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'lines_to_remove': {'type': 'list', 'required': True, 'description': 'Line series names to remove'},
                    'line_field': {'type': 'str', 'required': False, 'description': 'Line grouping field (optional, auto-detect)'}
                }
            },
            'show_moving_average': {
                'function': line_chart_tools.show_moving_average,
                'category': 'analysis',
                'description': 'Overlay moving average',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'window_size': {'type': 'int', 'required': False, 'default': 3, 'description': 'Moving average window size'}
                }
            },
            'focus_lines': {
                'function': line_chart_tools.focus_lines,
                'category': 'action',
                'description': 'Focus selected lines; dim or hide others',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'lines': {'type': 'list', 'required': True, 'description': 'Line series names to focus'},
                    'line_field': {'type': 'str', 'required': False, 'description': 'Line grouping field (optional, auto-detect)'},
                    'mode': {'type': 'str', 'required': False, 'default': 'dim', 'description': 'dim | hide'},
                    'dim_opacity': {'type': 'float', 'required': False, 'default': 0.08, 'description': 'Opacity for non-focused lines when mode=dim'}
                }
            },
            'drill_down_x_axis': {
                'function': line_chart_tools.drill_down_x_axis,
                'category': 'action',
                'description': 'Temporal drill-down (year→month→day) for finer-grained patterns',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'level': {'type': 'str', 'required': True, 'description': '"year" | "month" | "date"'},
                    'value': {'type': 'int', 'required': True, 'description': 'Year (2020-2030) | month (1-12) | day (1-31); must be int'},
                    'parent': {'type': 'dict', 'required': False, 'description': 'Parent context, e.g. {"year": 2023} or {"year": 2023, "month": 3}'}
                }
            },
            'reset_drilldown_x_axis': {
                'function': line_chart_tools.reset_drilldown_x_axis,
                'category': 'action',
                'description': 'Reset line chart drill-down to the initial year view',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'resample_x_axis': {
                'function': line_chart_tools.resample_x_axis,
                'category': 'action',
                'description': 'Change time granularity (resample): aggregate from fine to coarse (day→week→month→quarter→year)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'granularity': {'type': 'str', 'required': True, 'description': '"day" | "week" | "month" | "quarter" | "year"'},
                    'agg': {'type': 'str', 'required': False, 'default': 'mean', 'description': '"mean" | "sum" | "max" | "min" | "median"'}
                }
            },
            'reset_resample_x_axis': {
                'function': line_chart_tools.reset_resample_x_axis,
                'category': 'action',
                'description': 'Reset resampling to original granularity',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'change_encoding': {
                'function': line_chart_tools.change_encoding,
                'category': 'action',
                'description': 'Change field mapping for an encoding channel (color, size, shape, opacity, x, y, ...)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'channel': {'type': 'str', 'required': True, 'description': 'Encoding channel (color, size, shape, opacity, x, y, ...)'},
                    'field': {'type': 'str', 'required': True, 'description': 'New field name'},
                    'type': {'type': 'str', 'required': False, 'description': 'Optional type: quantitative | nominal | ordinal | temporal'}
                }
            }
        }
        
        # Scatter plot tools
        scatter_tools = {
            'identify_clusters': {
                'function': scatter_plot_tools.identify_clusters,
                'category': 'analysis',
                'description': 'Identify clusters',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'n_clusters': {'type': 'int', 'required': False, 'default': 3},
                    'method': {'type': 'str', 'required': False, 'default': 'kmeans'}
                }
            },
            'calculate_correlation': {
                'function': scatter_plot_tools.calculate_correlation,
                'category': 'analysis',
                'description': 'Compute correlation',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'method': {'type': 'str', 'required': False, 'default': 'pearson'}
                }
            },
            'zoom_2d_region': {
                'function': scatter_plot_tools.zoom_2d_region,
                'category': 'action',
                'description': 'Zoom into a dense region',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_range': {'type': 'tuple', 'required': True},
                    'y_range': {'type': 'tuple', 'required': True}
                }
            },
            'select_region': {
                'function': scatter_plot_tools.select_region,
                'category': 'action',
                'description': 'Select a region',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_range': {'type': 'tuple', 'required': True},
                    'y_range': {'type': 'tuple', 'required': True}
                }
            },
            'filter_categorical': {
                'function': scatter_plot_tools.filter_categorical,
                'category': 'action',
                'description': 'Filter out points in given categories',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'categories_to_remove': {'type': 'list', 'required': True, 'description': 'Category values to remove'},
                    'field': {'type': 'str', 'required': False, 'description': 'Category field (optional, auto-detect)'}
                }
            },
            'brush_region': {
                'function': scatter_plot_tools.brush_region,
                'category': 'action',
                'description': 'Brush a region; fade points outside',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_range': {'type': 'tuple', 'required': True, 'description': 'X range (min, max)'},
                    'y_range': {'type': 'tuple', 'required': True, 'description': 'Y range (min, max)'}
                }
            },
            'show_regression': {
                'function': scatter_plot_tools.show_regression,
                'category': 'analysis',
                'description': 'Overlay regression line',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'method': {'type': 'str', 'required': False, 'default': 'linear', 'description': 'Regression method (linear, log, exp, poly, quad)'}
                }
            },
            'change_encoding': {
                'function': scatter_plot_tools.change_encoding,
                'category': 'action',
                'description': 'Change field mapping for an encoding channel (color, size, shape, opacity, x, y, ...)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'channel': {'type': 'str', 'required': True, 'description': 'Encoding channel (color, size, shape, opacity, x, y, ...)'},
                    'field': {'type': 'str', 'required': True, 'description': 'New field name'},
                    'type': {'type': 'str', 'required': False, 'description': 'Optional type: quantitative | nominal | ordinal | temporal'}
                }
            }
        }
        
        # Heatmap tools
        heatmap_tools_dict = {
            'adjust_color_scale': {
                'function': heatmap_tools.adjust_color_scale,
                'category': 'action',
                'description': 'Adjust color scale and domain',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'scheme': {'type': 'str', 'required': False, 'default': 'viridis', 'description': 'Color scheme'},
                    'domain': {'type': 'list', 'required': False, 'description': 'Numeric domain [min, max]'}
                }
            },
            'filter_cells': {
                'function': heatmap_tools.filter_cells,
                'category': 'action',
                'description': 'Filter cells by color-field value; provide at least one of min_value or max_value (one-sided OK)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'min_value': {'type': 'float', 'required': False, 'description': 'Lower bound (inclusive); if only this, keep >= min_value'},
                    'max_value': {'type': 'float', 'required': False, 'description': 'Upper bound (inclusive); if only this, keep <= max_value'}
                }
            },
            'filter_cells_by_region': {
                'function': heatmap_tools.filter_cells_by_region,
                'category': 'action',
                'description': 'Remove aggregated heatmap cells by (x,y) coordinates via transform.filter. Provide x or y (or lists).',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_value': {'type': 'any', 'required': False, 'description': 'Single x to filter; use x_values for multiple'},
                    'y_value': {'type': 'any', 'required': False, 'description': 'Single y to filter; use y_values for multiple'},
                    'x_values': {'type': 'list', 'required': False, 'description': 'X values to filter out'},
                    'y_values': {'type': 'list', 'required': False, 'description': 'Y values to filter out'}
                }
            },
            'highlight_region': {
                'function': heatmap_tools.highlight_region,
                'category': 'action',
                'description': 'Highlight region: provide x_values and/or y_values (column, row, or intersection)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_values': {'type': 'list', 'required': False, 'description': 'X values to highlight'},
                    'y_values': {'type': 'list', 'required': False, 'description': 'Y values to highlight'}
                }
            },
            'highlight_region_by_value': {
                'function': heatmap_tools.highlight_region_by_value,
                'category': 'action',
                'description': 'Highlight by cell value: in-range unchanged, out-of-range faded (no deletion; one-sided thresholds OK)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'min_value': {'type': 'float', 'required': False, 'description': 'Lower threshold (optional)'},
                    'max_value': {'type': 'float', 'required': False, 'description': 'Upper threshold (optional)'},
                    'outside_opacity': {'type': 'float', 'required': False, 'default': 0.12, 'description': 'Opacity outside range'}
                }
            },
            'cluster_rows_cols': {
                'function': heatmap_tools.cluster_rows_cols,
                'category': 'action',
                'description': 'Cluster-sort rows and/or columns',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'cluster_rows': {'type': 'bool', 'required': False, 'default': True},
                    'cluster_cols': {'type': 'bool', 'required': False, 'default': True},
                    'method': {'type': 'str', 'required': False, 'default': 'sum'}
                }
            },
            'select_submatrix': {
                'function': heatmap_tools.select_submatrix,
                'category': 'action',
                'description': 'Select a submatrix',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'x_values': {'type': 'list', 'required': False},
                    'y_values': {'type': 'list', 'required': False}
                }
            },
            'find_extremes': {
                'function': heatmap_tools.find_extremes,
                'category': 'analysis',
                'description': 'Mark extreme cell positions',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'top_n': {'type': 'int', 'required': False, 'default': 5, 'description': 'Top N extremes to mark'},
                    'mode': {'type': 'str', 'required': False, 'default': 'both', 'description': 'max | min | both'}
                }
            },
            'threshold_mask': {
                'function': heatmap_tools.threshold_mask,
                'category': 'action',
                'description': 'Threshold mask: fade cells outside range (no deletion)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'min_value': {'type': 'float', 'required': True, 'description': 'Lower threshold (inclusive)'},
                    'max_value': {'type': 'float', 'required': True, 'description': 'Upper threshold (inclusive)'},
                    'outside_opacity': {'type': 'float', 'required': False, 'default': 0.1, 'description': 'Opacity outside range'}
                }
            },
            'drilldown_axis': {
                'function': heatmap_tools.drilldown_axis,
                'category': 'action',
                'description': 'Temporal heatmap drill-down: year→month→day',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'level': {'type': 'str', 'required': True, 'description': 'year | month | date'},
                    'value': {'type': 'any', 'required': True, 'description': 'Value for level (year=int, month=1-12, date=1-31)'},
                    'parent': {'type': 'dict', 'required': False, 'description': 'Parent context, e.g. {\"year\":2012} or {\"year\":2012,\"month\":3}'}
                }
            },
            'reset_drilldown': {
                'function': heatmap_tools.reset_drilldown,
                'category': 'action',
                'description': 'Reset temporal heatmap drill-down to initial granularity',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'add_marginal_bars': {
                'function': heatmap_tools.add_marginal_bars,
                'category': 'action',
                'description': 'Add marginal bar charts (row/column aggregates, default mean) to compare overall levels',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'op': {'type': 'str', 'required': False, 'default': 'mean', 'description': 'Aggregate: mean (default) | sum | median | max | min | count'},
                    'show_top': {'type': 'bool', 'required': False, 'default': True, 'description': 'Show top margin bars (aggregate by column/x)'},
                    'show_right': {'type': 'bool', 'required': False, 'default': True, 'description': 'Show right margin bars (aggregate by row/y)'},
                    'bar_size': {'type': 'int', 'required': False, 'default': 70, 'description': 'Margin bar thickness in pixels'},
                    'bar_color': {'type': 'str', 'required': False, 'default': '#666666', 'description': 'Margin bar color'}
                }
            },
            'transpose': {
                'function': heatmap_tools.transpose,
                'category': 'action',
                'description': 'Transpose heatmap: swap x and y axes',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'change_encoding': {
                'function': heatmap_tools.change_encoding,
                'category': 'action',
                'description': 'Change field mapping for an encoding channel (color, size, shape, opacity, x, y, ...)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'channel': {'type': 'str', 'required': True, 'description': 'Encoding channel (color, size, shape, opacity, x, y, ...)'},
                    'field': {'type': 'str', 'required': True, 'description': 'New field name'},
                    'type': {'type': 'str', 'required': False, 'description': 'Optional type: quantitative | nominal | ordinal | temporal'}
                }
            }
        }
        
        # Parallel coordinates tools
        parallel_coords_tools_dict = {
            'reorder_dimensions': {
                'function': parallel_coordinates_tools.reorder_dimensions,
                'category': 'action',
                'description': 'Reorder dimensions',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'dimension_order': {'type': 'list', 'required': True}
                }
            },
            'filter_by_category': {
                'function': parallel_coordinates_tools.filter_by_category,
                'category': 'action',
                'description': 'Filter data by categorical field',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'field': {'type': 'str', 'required': True, 'description': 'Categorical field name'},
                    'values': {'type': 'str|list', 'required': True, 'description': 'Values to exclude'}
                }
            },
            'highlight_category': {
                'function': parallel_coordinates_tools.highlight_category,
                'category': 'action',
                'description': 'Highlight categories; dim others',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'field': {'type': 'str', 'required': True, 'description': 'Categorical field name'},
                    'values': {'type': 'str|list', 'required': True, 'description': 'Values to highlight'}
                }
            },
            'hide_dimensions': {
                'function': parallel_coordinates_tools.hide_dimensions,
                'category': 'action',
                'description': 'Hide or show dimension axes (useful when there are many dimensions)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'dimensions': {'type': 'list', 'required': True, 'description': 'Dimension names to hide or show'},
                    'mode': {'type': 'str', 'required': False, 'default': 'hide', 'description': '"hide" or "show"'}
                }
            },
            'reset_hidden_dimensions': {
                'function': parallel_coordinates_tools.reset_hidden_dimensions,
                'category': 'action',
                'description': 'Reset hidden dimensions so all are visible',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            }
        }
        
        # Sankey tools
        sankey_tools_dict = {
            'get_node_options': {
                'function': sankey_tools.get_node_options,
                'category': 'perception',
                'description': 'List all node names and layer info for the Sankey. Call before highlight_path, trace_node, color_flows, etc., so names match the chart (avoid invalid names like Homepage/Electronics).',
                'params': {
                    'state': {'type': 'dict', 'required': True}
                }
            },
            'filter_flow': {
                'function': sankey_tools.filter_flow,
                'category': 'action',
                'description': 'Filter flows: show only links with flow >= threshold',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'min_value': {'type': 'float', 'required': True, 'description': 'Minimum flow threshold'}
                }
            },
            'highlight_path': {
                'function': sankey_tools.highlight_path,
                'category': 'action',
                'description': 'Highlight multi-step path: all links between adjacent nodes on the path',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'path': {'type': 'list', 'required': True, 'description': 'Node path, e.g. ["A", "B", "C", "D"]'}
                }
            },
            'calculate_conversion_rate': {
                'function': sankey_tools.calculate_conversion_rate,
                'category': 'analysis',
                'description': 'Compute conversion: inflow, outflow, and rate per node',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'node_name': {'type': 'str', 'required': False, 'description': 'Optional node name; omit for all nodes'}
                }
            },
            'trace_node': {
                'function': sankey_tools.trace_node,
                'category': 'action',
                'description': 'Trace node: highlight all links connected to it',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'node_name': {'type': 'str', 'required': True, 'description': 'Node name to trace'}
                }
            },
            'collapse_nodes': {
                'function': sankey_tools.collapse_nodes,
                'category': 'action',
                'description': 'Collapse nodes: merge multiple into one aggregate',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'nodes_to_collapse': {'type': 'list', 'required': True, 'description': 'Node names to collapse'},
                    'aggregate_name': {'type': 'str', 'required': False, 'default': 'Other', 'description': 'Name for aggregate node'}
                }
            },
            'expand_node': {
                'function': sankey_tools.expand_node,
                'category': 'action',
                'description': 'Expand aggregate node back into original nodes',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'aggregate_name': {'type': 'str', 'required': True, 'description': 'Aggregate node name to expand'}
                }
            },
            'auto_collapse_by_rank': {
                'function': sankey_tools.auto_collapse_by_rank,
                'category': 'action',
                'description': 'Auto-collapse by rank: keep top N nodes per layer, fold rest into Others',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'top_n': {'type': 'int', 'required': False, 'default': 5, 'description': 'Nodes to keep per layer'}
                }
            },
            'color_flows': {
                'function': sankey_tools.color_flows,
                'category': 'action',
                'description': 'Color flows connected to given nodes',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'nodes': {'type': 'list', 'required': True, 'description': 'Nodes whose incident flows are colored'},
                    'color': {'type': 'str', 'required': False, 'default': '#e74c3c', 'description': 'Color'}
                }
            },
            'find_bottleneck': {
                'function': sankey_tools.find_bottleneck,
                'category': 'analysis',
                'description': 'Find bottleneck nodes (largest drop-off)',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'top_n': {'type': 'int', 'required': False, 'default': 3, 'description': 'Top N bottleneck nodes'}
                }
            },
            'reorder_nodes_in_layer': {
                'function': sankey_tools.reorder_nodes_in_layer,
                'category': 'action',
                'description': 'Reorder nodes within a Sankey layer (reduces crossings). Must set depth (0=leftmost) and exactly one of order or sort_by.',
                'params': {
                    'state': {'type': 'dict', 'required': True},
                    'depth': {'type': 'int', 'required': True, 'description': 'Layer index: 0=leftmost, 1=next, ...'},
                    'order': {'type': 'list', 'required': False, 'description': 'Node names top-to-bottom; mutually exclusive with sort_by'},
                    'sort_by': {'type': 'str', 'required': False, 'description': 'Mutually exclusive with order: value_desc | value_asc | name'}
                }
            }
        }
        
        # Register all tools
        for name, info in common_tools.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in bar_chart_tools_dict.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in line_chart_tools_dict.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in scatter_tools.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in heatmap_tools_dict.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in parallel_coords_tools_dict.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        for name, info in sankey_tools_dict.items():
            self._tools[name] = self._wrap_tool_info(info)
        
        # Map chart types to tools
        self._chart_tools[ChartType.BAR_CHART] = list(bar_chart_tools_dict.keys()) + list(common_tools.keys())
        self._chart_tools[ChartType.LINE_CHART] = list(line_chart_tools_dict.keys()) + list(common_tools.keys())
        self._chart_tools[ChartType.SCATTER_PLOT] = list(scatter_tools.keys()) + list(common_tools.keys())
        self._chart_tools[ChartType.HEATMAP] = list(heatmap_tools_dict.keys()) + list(common_tools.keys())
        self._chart_tools[ChartType.PARALLEL_COORDINATES] = list(parallel_coords_tools_dict.keys()) + list(common_tools.keys())
        # Sankey is Vega format without encoding.x/y; get_tooltip_data is omitted for agents
        _common_for_sankey = [k for k in common_tools.keys() if k != 'get_tooltip_data']
        self._chart_tools[ChartType.SANKEY_DIAGRAM] = list(sankey_tools_dict.keys()) + _common_for_sankey
    
    def get_tool(self, tool_name: str) -> Dict[str, Any]:
        """Return tool metadata by name."""
        return self._tools.get(tool_name)

    def _wrap_tool_info(self, info: Dict[str, Any]) -> Dict[str, Any]:
        wrapped = dict(info)
        fn = wrapped.get("function")
        if callable(fn):
            wrapped["function"] = tool_output(fn)
        return wrapped
    
    def list_tools_for_chart(self, chart_type: ChartType) -> List[str]:
        """List tool names available for a chart type."""
        return self._chart_tools.get(chart_type, list(self._tools.keys()))
    
    def list_all_tools(self) -> List[str]:
        """List all tool names."""
        return list(self._tools.keys())

    def list_tool_descriptors_for_chart(self, chart_type: ChartType) -> List[Dict[str, Any]]:
        """Return serializable tool descriptors for prompts/runtime export."""
        names = self.list_tools_for_chart(chart_type)
        out: List[Dict[str, Any]] = []
        for name in names:
            info = self.get_tool(name) or {}
            out.append(
                {
                    "name": name,
                    "category": info.get("category", "action"),
                    "description": info.get("description", ""),
                    "params": info.get("params", {}),
                    "custom": name in self._custom_tools,
                }
            )
        return out

    def register_tool(
        self,
        *,
        name: str,
        function: Callable[..., Any],
        category: str,
        description: str,
        params: Optional[Dict[str, Any]] = None,
        chart_types: Optional[List[ChartType]] = None,
        override: bool = False,
    ) -> None:
        """Register a custom tool so runtime/agent can discover and call it.

        This is backward-compatible: existing built-in tools keep working unchanged.
        """
        if (not override) and name in self._tools:
            raise ValueError(f"tool '{name}' already exists; pass override=True to replace")

        info = self._wrap_tool_info(
            {
                "function": function,
                "category": category,
                "description": description,
                "params": params or {},
            }
        )
        self._tools[name] = info
        self._custom_tools[name] = info

        if chart_types:
            for ct in chart_types:
                self._chart_tools.setdefault(ct, [])
                if name not in self._chart_tools[ct]:
                    self._chart_tools[ct].append(name)
                self._custom_chart_tools.setdefault(ct, [])
                if name not in self._custom_chart_tools[ct]:
                    self._custom_chart_tools[ct].append(name)

    def unregister_tool(self, name: str) -> bool:
        """Unregister previously added custom tool. Built-in tools are protected."""
        if name not in self._custom_tools:
            return False

        self._custom_tools.pop(name, None)
        self._tools.pop(name, None)

        for ct, tool_names in self._chart_tools.items():
            if name in tool_names:
                self._chart_tools[ct] = [n for n in tool_names if n != name]
        for ct, tool_names in self._custom_chart_tools.items():
            if name in tool_names:
                self._custom_chart_tools[ct] = [n for n in tool_names if n != name]
        return True

    def list_custom_tools(self) -> List[str]:
        """List names of runtime-registered (non built-in) tools."""
        return list(self._custom_tools.keys())



tool_registry = ToolRegistry()
