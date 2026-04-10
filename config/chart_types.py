"""
Chart type enum and configuration for supported visualizations.
"""

from enum import Enum
from typing import List, Dict, Any
from dataclasses import dataclass


class ChartType(Enum):
    """Supported chart kinds."""
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    SCATTER_PLOT = "scatter_plot"
    PARALLEL_COORDINATES = "parallel_coordinates"
    HEATMAP = "heatmap"
    SANKEY_DIAGRAM = "sankey_diagram"
    UNKNOWN = "unknown"

    def __str__(self):
        return self.value

    @classmethod
    def from_string(cls, chart_type: str) -> 'ChartType':
        """Parse enum from string."""
        chart_type_lower = chart_type.lower().replace(' ', '_').replace('-', '_')
        for ct in cls:
            if ct.value == chart_type_lower:
                return ct
        return cls.UNKNOWN


@dataclass
class ChartTypeConfig:
    """Metadata for a chart type."""
    name: str
    display_name: str
    description: str
    typical_marks: List[str]
    typical_encodings: List[str]
    supported_interactions: List[str]
    prompt_file: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'typical_marks': self.typical_marks,
            'typical_encodings': self.typical_encodings,
            'supported_interactions': self.supported_interactions,
            'prompt_file': self.prompt_file
        }


CHART_TYPE_CONFIGS = {
    ChartType.BAR_CHART: ChartTypeConfig(
        name="bar_chart",
        display_name="Bar chart",
        description="Compare values across categories",
        typical_marks=["bar"],
        typical_encodings=["x", "y", "color"],
        supported_interactions=["sort", "filter", "highlight", "compare"],
        prompt_file="bar_chart.txt"
    ),

    ChartType.LINE_CHART: ChartTypeConfig(
        name="line_chart",
        display_name="Line chart",
        description="Trends and time series",
        typical_marks=["line", "point"],
        typical_encodings=["x", "y", "color"],
        supported_interactions=["zoom", "time_range", "trend_detection", "compare"],
        prompt_file="line_chart.txt"
    ),

    ChartType.SCATTER_PLOT: ChartTypeConfig(
        name="scatter_plot",
        display_name="Scatter plot",
        description="Relationship and distribution of two variables",
        typical_marks=["point", "circle"],
        typical_encodings=["x", "y", "color", "size"],
        supported_interactions=["select", "cluster", "correlation", "zoom"],
        prompt_file="scatter_plot.txt"
    ),

    ChartType.PARALLEL_COORDINATES: ChartTypeConfig(
        name="parallel_coordinates",
        display_name="Parallel coordinates",
        description="Multivariate patterns",
        typical_marks=["line"],
        typical_encodings=["x", "y", "color"],
        supported_interactions=["reorder", "brush", "highlight"],
        prompt_file="parallel_coordinates.txt"
    ),

    ChartType.HEATMAP: ChartTypeConfig(
        name="heatmap",
        display_name="Heatmap",
        description="Matrix values and correlation",
        typical_marks=["rect"],
        typical_encodings=["x", "y", "color"],
        supported_interactions=["color_scale", "select_submatrix", "cluster"],
        prompt_file="heatmap.txt"
    ),

    ChartType.SANKEY_DIAGRAM: ChartTypeConfig(
        name="sankey_diagram",
        display_name="Sankey diagram",
        description="Flows and conversions",
        typical_marks=["rect", "path"],
        typical_encodings=["x", "y", "color", "opacity"],
        supported_interactions=["filter_flow", "highlight_path", "trace_node"],
        prompt_file="sankey_diagram.txt"
    )
}


def get_chart_config(chart_type: ChartType) -> ChartTypeConfig:
    return CHART_TYPE_CONFIGS.get(chart_type, None)


def get_all_chart_types() -> List[ChartType]:
    return [ct for ct in ChartType if ct != ChartType.UNKNOWN]


def get_chart_type_by_mark(mark: str) -> ChartType:
    """Infer chart type from Vega-Lite mark name."""
    mark = mark.lower()
    for chart_type, config in CHART_TYPE_CONFIGS.items():
        if mark in config.typical_marks:
            return chart_type
    return ChartType.UNKNOWN


def get_supported_interactions(chart_type: ChartType) -> List[str]:
    config = get_chart_config(chart_type)
    return config.supported_interactions if config else []


def get_candidate_chart_types(vega_spec: Dict[str, Any]) -> List[ChartType]:
    """
    Infer likely chart types from a Vega-Lite spec.

    Args:
        vega_spec: Vega-Lite JSON dict

    Returns:
        Ordered list of candidate chart types.
    """
    candidates = []

    mark = vega_spec.get('mark')
    if isinstance(mark, dict):
        mark_type = mark.get('type', '')
    else:
        mark_type = mark or ''

    mark_type = str(mark_type).lower()

    encoding = vega_spec.get('encoding', {})
    x_encoding = encoding.get('x', {})
    y_encoding = encoding.get('y', {})
    x_type = x_encoding.get('type', '')
    y_type = y_encoding.get('type', '')

    if mark_type == 'point':
        if x_type == 'temporal':
            candidates.append(ChartType.LINE_CHART)
        elif x_type == 'quantitative' and y_type == 'quantitative':
            candidates.append(ChartType.SCATTER_PLOT)
        elif 'shape' in encoding or 'size' in encoding:
            candidates.append(ChartType.SCATTER_PLOT)
        else:
            candidates.append(ChartType.SCATTER_PLOT)
            candidates.append(ChartType.LINE_CHART)

    elif mark_type:
        chart_type = get_chart_type_by_mark(mark_type)
        if chart_type != ChartType.UNKNOWN:
            candidates.append(chart_type)

    if not candidates:
        if 'x' in encoding and 'y' in encoding:
            if x_type == 'temporal' or y_type == 'temporal':
                candidates.append(ChartType.LINE_CHART)

            if x_type == 'nominal' and y_type == 'quantitative':
                candidates.append(ChartType.BAR_CHART)
            elif x_type == 'quantitative' and y_type == 'quantitative':
                candidates.append(ChartType.SCATTER_PLOT)

        if 'color' in encoding:
            color_type = encoding.get('color', {}).get('type', '')
            if color_type == 'quantitative':
                candidates.append(ChartType.HEATMAP)

    if not candidates:
        candidates.append(ChartType.UNKNOWN)

    return candidates
