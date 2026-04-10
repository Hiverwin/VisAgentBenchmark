"""Preset widget analyzer factories for all supported chart types."""

from typing import Any, Dict

from config.chart_types import ChartType
from packages.widget_sdk.scatter_analyzer import WidgetAgentAnalyzer


def _preset_bar_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": "bar",
        "encoding": {
            "x": {"field": "category", "type": "nominal"},
            "y": {"field": "value", "type": "quantitative"},
            "color": {"field": "group", "type": "nominal"},
        },
        "data": {"values": [{"category": "A", "value": 10, "group": "G1"}, {"category": "B", "value": 18, "group": "G2"}]},
    }


def _preset_line_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "date", "type": "temporal"},
            "y": {"field": "value", "type": "quantitative"},
            "color": {"field": "series", "type": "nominal"},
        },
        "data": {
            "values": [
                {"date": "2025-01-01", "value": 10, "series": "S1"},
                {"date": "2025-02-01", "value": 14, "series": "S1"},
                {"date": "2025-01-01", "value": 8, "series": "S2"},
                {"date": "2025-02-01", "value": 12, "series": "S2"},
            ]
        },
    }


def _preset_scatter_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": {"type": "point", "filled": True, "size": 90},
        "encoding": {
            "x": {"field": "horsepower", "type": "quantitative"},
            "y": {"field": "miles_per_gallon", "type": "quantitative"},
            "color": {"field": "origin", "type": "nominal"},
        },
        "data": {
            "values": [
                {"horsepower": 130, "miles_per_gallon": 18, "origin": "USA"},
                {"horsepower": 95, "miles_per_gallon": 25, "origin": "Japan"},
                {"horsepower": 150, "miles_per_gallon": 16, "origin": "USA"},
                {"horsepower": 88, "miles_per_gallon": 30, "origin": "Europe"},
                {"horsepower": 110, "miles_per_gallon": 22, "origin": "Japan"},
            ]
        },
    }


def _preset_heatmap_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": "rect",
        "encoding": {
            "x": {"field": "x", "type": "ordinal"},
            "y": {"field": "y", "type": "ordinal"},
            "color": {"field": "value", "type": "quantitative"},
        },
        "data": {"values": [{"x": "A", "y": "P", "value": 3}, {"x": "A", "y": "Q", "value": 8}, {"x": "B", "y": "P", "value": 5}, {"x": "B", "y": "Q", "value": 1}]},
    }


def _preset_parallel_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"a": 1, "b": 4, "c": 2, "group": "G1"}, {"a": 3, "b": 2, "c": 5, "group": "G2"}]},
        "transform": [{"fold": ["a", "b", "c"], "as": ["dimension", "value"]}],
        "mark": "line",
        "encoding": {
            "x": {"field": "dimension", "type": "nominal"},
            "y": {"field": "value", "type": "quantitative"},
            "detail": {"field": "group", "type": "nominal"},
            "color": {"field": "group", "type": "nominal"},
        },
    }


def _preset_sankey_spec() -> Dict[str, Any]:
    # Minimal Vega-style sankey-like graph structure used as placeholder preset.
    return {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "data": [
            {
                "name": "nodes",
                "values": [
                    {"name": "Start", "depth": 0},
                    {"name": "A", "depth": 1},
                    {"name": "B", "depth": 1},
                    {"name": "End", "depth": 2},
                ],
            },
            {
                "name": "links",
                "values": [
                    {"source": "Start", "target": "A", "value": 6},
                    {"source": "Start", "target": "B", "value": 4},
                    {"source": "A", "target": "End", "value": 6},
                    {"source": "B", "target": "End", "value": 4},
                ],
            },
        ],
    }


_PRESET_BUILDERS = {
    ChartType.BAR_CHART: _preset_bar_spec,
    ChartType.LINE_CHART: _preset_line_spec,
    ChartType.SCATTER_PLOT: _preset_scatter_spec,
    ChartType.HEATMAP: _preset_heatmap_spec,
    ChartType.PARALLEL_COORDINATES: _preset_parallel_spec,
    ChartType.SANKEY_DIAGRAM: _preset_sankey_spec,
}


def create_preset_widget_analyzer(chart_type: str) -> WidgetAgentAnalyzer:
    ct = ChartType.from_string(chart_type)
    if ct not in _PRESET_BUILDERS:
        raise ValueError(f"unsupported preset chart_type: {chart_type}")
    return WidgetAgentAnalyzer(vega_spec=_PRESET_BUILDERS[ct](), chart_type=str(ct))


def create_preset_bar_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.BAR_CHART))


def create_preset_line_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.LINE_CHART))


def create_preset_scatter_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.SCATTER_PLOT))


def create_preset_heatmap_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.HEATMAP))


def create_preset_parallel_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.PARALLEL_COORDINATES))


def create_preset_sankey_analyzer() -> WidgetAgentAnalyzer:
    return create_preset_widget_analyzer(str(ChartType.SANKEY_DIAGRAM))

