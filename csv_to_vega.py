"""
CSV to Vega/Vega-Lite converter.

Supported chart kinds: scatter, bar, line, parallel coordinates, heatmap, sankey.
"""

import json
import pandas as pd
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path


ChartType = Literal["scatter", "bar", "line", "parallel", "heatmap", "sankey"]


class VegaConverter:
    """Build Vega/Vega-Lite specs from a CSV file."""
    
    def __init__(self, csv_path: str):
        """
        
        
        Args:
            csv_path: CSV
        """
        self.csv_path = csv_path
        self.dataset_name = Path(csv_path).stem
        self.df = pd.read_csv(csv_path)
        self.data = self.df.to_dict(orient="records")
        
        # 
        self.numeric_cols = self.df.select_dtypes(include=['number']).columns.tolist()
        self.categorical_cols = self.df.select_dtypes(include=['object', 'category']).columns.tolist()
        self.datetime_cols = []
        
        # 
        for col in self.categorical_cols[:]:
            try:
                pd.to_datetime(self.df[col])
                self.datetime_cols.append(col)
                self.categorical_cols.remove(col)
            except:
                pass
    
    def get_column_info(self) -> Dict[str, List[str]]:
        """Return inferred numeric/categorical/datetime column lists."""
        return {
            "numeric": self.numeric_cols,
            "categorical": self.categorical_cols,
            "datetime": self.datetime_cols,
            "all": self.df.columns.tolist()
        }
    
    def convert(
        self,
        chart_type: ChartType,
        x: Optional[str] = None,
        y: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
        columns: Optional[List[str]] = None,
        normalize: bool = False,
        source: Optional[str] = None,
        target: Optional[str] = None,
        value: Optional[str] = None,
        title: Optional[str] = None,
        width: int = 600,
        height: int = 400
    ) -> Dict[str, Any]:
        """
        Build a Vega or Vega-Lite spec from the loaded CSV.

        Args:
            chart_type: One of scatter, bar, line, parallel, heatmap, sankey.
            x, y, color, size: Encoding fields where applicable.
            columns: For parallel coordinates.
            normalize: Normalize parallel coordinate dimensions.
            source, target, value: Sankey link fields.
            title, width, height: Chart metadata and size.

        Returns:
            A Vega-Lite or Vega spec dict.
        """
        if chart_type == "scatter":
            return self._create_scatter(x, y, color, size, title, width, height)
        elif chart_type == "bar":
            return self._create_bar(x, y, color, title, width, height)
        elif chart_type == "line":
            return self._create_line(x, y, color, title, width, height)
        elif chart_type == "parallel":
            return self._create_parallel_coordinates(columns, color, normalize, title, width, height)
        elif chart_type == "heatmap":
            return self._create_heatmap(x, y, color, title, width, height)
        elif chart_type == "sankey":
            return self._create_sankey(source, target, value, title, width, height)
        else:
            raise ValueError(f"Unsupported chart type: {chart_type}")
    
    def _auto_select_columns(self, prefer_numeric: bool = True, count: int = 2) -> List[str]:
        """Pick default columns for plotting."""
        if prefer_numeric and len(self.numeric_cols) >= count:
            return self.numeric_cols[:count]
        elif len(self.categorical_cols) >= 1 and len(self.numeric_cols) >= 1:
            return [self.categorical_cols[0], self.numeric_cols[0]]
        return self.df.columns.tolist()[:count]
    
    def _get_field_type(self, field: str) -> str:
        """Vega-Lite"""
        if field in self.numeric_cols:
            return "quantitative"
        elif field in self.datetime_cols:
            return "temporal"
        elif field in self.categorical_cols:
            return "nominal"
        else:
            return "nominal"
    
    def _create_scatter(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        size: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega-Lite)"""
        cols = self._auto_select_columns(prefer_numeric=True, count=2)
        x = x or cols[0]
        y = y or (cols[1] if len(cols) > 1 else cols[0])
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Scatter Plot: {x} vs {y}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": {"type": "point", "filled": True, "opacity": 0.7},
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        if size:
            spec["encoding"]["size"] = {
                "field": size,
                "type": self._get_field_type(size)
            }
        
        return spec
    
    def _create_bar(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega-Lite)"""
        # 
        if not x:
            x = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not y:
            y = self.numeric_cols[0] if self.numeric_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Bar Chart: {y} by {x}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": "bar",
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        # y，
        if y in self.numeric_cols and x in self.categorical_cols:
            spec["encoding"]["y"]["aggregate"] = "mean"
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        return spec
    
    def _create_line(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega-Lite)"""
        # x
        if not x:
            if self.datetime_cols:
                x = self.datetime_cols[0]
            elif self.categorical_cols:
                x = self.categorical_cols[0]
            else:
                x = self.df.columns[0]
        
        if not y:
            y = self.numeric_cols[0] if self.numeric_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Line Chart: {y} over {x}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": x, "type": self._get_field_type(x)},
                "y": {"field": y, "type": self._get_field_type(y)}
            }
        }
        
        if color:
            spec["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
        
        return spec
    
    def _create_parallel_coordinates(
        self,
        columns: Optional[List[str]],
        color: Optional[str],
        normalize: bool,
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega-Lite)"""
        # 
        if not columns:
            columns = self.numeric_cols[:5] if len(self.numeric_cols) >= 2 else self.df.columns.tolist()[:5]
        
        if len(columns) < 2:
            raise ValueError("Parallel coordinates need at least 2 numeric columns")

        #  200 ， _metadata 
        PARALLEL_VIEW_LIMIT = 200
        total_rows = len(self.df)
        if total_rows > PARALLEL_VIEW_LIMIT:
            df_for_view = self.df.head(PARALLEL_VIEW_LIMIT)
        else:
            df_for_view = self.df

        # Vega-Literepeatlayer
        # 
        df_normalized = df_for_view[columns].copy()
        
        # （）
        if normalize:
            for col in columns:
                if col in self.numeric_cols:
                    min_val = df_normalized[col].min()
                    max_val = df_normalized[col].max()
                    if max_val != min_val:
                        df_normalized[col] = (df_normalized[col] - min_val) / (max_val - min_val)
                    else:
                        df_normalized[col] = 0.5
        
        # 
        df_normalized['_index'] = range(len(df_normalized))
        
        # ，
        if color and color in df_for_view.columns:
            df_normalized[color] = df_for_view[color]
        
        # 
        id_vars = ['_index']
        if color and color in df_normalized.columns and color not in columns:
            id_vars.append(color)
        
        # value_vars
        valid_columns = [c for c in columns if c in df_normalized.columns]
        
        value_field = "normalized_value" if normalize else "value"
        df_long = df_normalized.melt(
            id_vars=id_vars,
            value_vars=valid_columns,
            var_name='dimension',
            value_name=value_field
        )
        
        # （：min/mid/max）
        tick_records = []
        axis_records = []
        for col in valid_columns:
            axis_records.append({"dimension": col})
            if normalize:
                series = self.df[col]
                min_val = float(series.min())
                max_val = float(series.max())
                median_val = float(series.median())
                tick_map = {
                    "min": {"value": 0.0, "label": min_val},
                    "mid": {"value": 0.5, "label": median_val},
                    "max": {"value": 1.0, "label": max_val}
                }
            else:
                series = self.df[col]
                min_val = float(series.min())
                max_val = float(series.max())
                mid_val = (min_val + max_val) / 2
                tick_map = {
                    "min": {"value": min_val, "label": min_val},
                    "mid": {"value": mid_val, "label": mid_val},
                    "max": {"value": max_val, "label": max_val}
                }
            
            for level, tick_info in tick_map.items():
                tick_records.append({
                    "dimension": col,
                    "tick_level": level,
                    "tick_value": float(tick_info["value"]),
                    "tick_label": float(tick_info["label"])
                })
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Parallel: {self.dataset_name}",
            "width": width,
            "height": height,
            "data": {"values": df_long.to_dict(orient="records")},
            "_metadata": {
                "view_limit": PARALLEL_VIEW_LIMIT,
                "total_count": total_rows,
                "displayed_count": len(df_for_view),
            },
            "encoding": {
                "x": {
                    "field": "dimension",
                    "type": "nominal",
                    "sort": valid_columns,
                    "axis": {"title": None, "labelAngle": 0}
                }
            },
            "layer": [
                {
                    "data": {"values": axis_records},
                    "mark": {"type": "rule", "color": "#ccc"},
                    "encoding": {}
                },
                {
                    "mark": {"type": "line", "opacity": 0.3, "strokeWidth": 1},
                    "encoding": {
                        "y": {
                            "field": value_field,
                            "type": "quantitative",
                            "axis": None
                        },
                        "detail": {"field": "_index", "type": "nominal"}
                    }
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'max'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'mid'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                },
                {
                    "data": {"values": tick_records},
                    "transform": [{"filter": "datum.tick_level === 'min'"}],
                    "encoding": {
                        "y": {
                            "field": "tick_value",
                            "type": "quantitative",
                            "axis": None
                        }
                    },
                    "layer": [
                        {
                            "mark": {"type": "text", "style": "label"},
                            "encoding": {"text": {"field": "tick_label", "type": "quantitative"}}
                        },
                        {
                            "mark": {"type": "tick", "style": "tick", "size": 8, "color": "#ccc"}
                        }
                    ]
                }
            ],
            "config": {
                "axisX": {"domain": False, "labelAngle": 0, "tickColor": "#ccc", "title": None},
                "view": {"stroke": None},
                "style": {
                    "label": {"baseline": "middle", "align": "right", "dx": -5},
                    "tick": {"orient": "horizontal"}
                }
            }
        }
        
        # 
        if color and color in df_long.columns:
            spec["layer"][1]["encoding"]["color"] = {
                "field": color,
                "type": self._get_field_type(color)
            }
            spec["layer"][1]["mark"]["opacity"] = 0.5
        
        return spec
    
    def _create_heatmap(
        self,
        x: Optional[str],
        y: Optional[str],
        color: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega-Lite)"""
        # 
        if not x:
            x = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not y:
            y = self.categorical_cols[1] if len(self.categorical_cols) > 1 else (
                self.categorical_cols[0] if self.categorical_cols else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
            )
        if not color:
            color = self.numeric_cols[0] if self.numeric_cols else "count"
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title or f"Heatmap: {color} by {x} and {y}",
            "width": width,
            "height": height,
            "data": {"values": self.data},
            "mark": "rect",
            "encoding": {
                "x": {"field": x, "type": "nominal"},
                "y": {"field": y, "type": "nominal"},
                "color": {
                    "aggregate": "mean" if color in self.numeric_cols else "count",
                    "field": color if color != "count" else None,
                    "type": "quantitative",
                    "scale": {"scheme": "blues"}
                }
            }
        }
        
        # colorcount，field
        if color == "count":
            spec["encoding"]["color"] = {
                "aggregate": "count",
                "type": "quantitative",
                "scale": {"scheme": "blues"}
            }
        
        return spec
    
    def _create_sankey(
        self,
        source: Optional[str],
        target: Optional[str],
        value: Optional[str],
        title: Optional[str],
        width: int,
        height: int
    ) -> Dict[str, Any]:
        """ (Vega)"""
        # source, target, value
        if not source:
            source = self.categorical_cols[0] if self.categorical_cols else self.df.columns[0]
        if not target:
            target = self.categorical_cols[1] if len(self.categorical_cols) > 1 else self.df.columns[1] if len(self.df.columns) > 1 else self.df.columns[0]
        if not value:
            value = self.numeric_cols[0] if self.numeric_cols else None
        
        # 
        # source-target
        if value:
            df_sankey = self.df.groupby([source, target])[value].sum().reset_index()
        else:
            df_sankey = self.df.groupby([source, target]).size().reset_index(name='value')
            value = 'value'
        
        # 
        nodes = list(set(df_sankey[source].tolist() + df_sankey[target].tolist()))
        node_map = {node: idx for idx, node in enumerate(nodes)}
        
        # 
        links_data = []
        for _, row in df_sankey.iterrows():
            links_data.append({
                "source": node_map[row[source]],
                "target": node_map[row[target]],
                "value": float(row[value])
            })
        
        nodes_data = [{"name": node} for node in nodes]
        
        spec = {
            "$schema": "https://vega.github.io/schema/vega/v5.json",
            "title": {"text": title or f"Sankey Diagram: {source} → {target}"},
            "width": width,
            "height": height,
            "padding": 10,
            "data": [
                {
                    "name": "nodes",
                    "values": nodes_data,
                    "transform": [
                        {"type": "identifier", "as": "id"}
                    ]
                },
                {
                    "name": "links",
                    "values": links_data
                }
            ],
            "scales": [
                {
                    "name": "color",
                    "type": "ordinal",
                    "domain": {"data": "nodes", "field": "name"},
                    "range": {"scheme": "category20"}
                }
            ],
            "marks": [
                {
                    "type": "group",
                    "from": {
                        "facet": {
                            "name": "sankey",
                            "data": "links",
                            "transform": [
                                {
                                    "type": "sankey",
                                    "extent": [{"signal": "[0, 0]"}, {"signal": "[width, height]"}],
                                    "nodeId": {"expr": "datum.id"},
                                    "nodeWidth": 10,
                                    "nodePadding": 10,
                                    "nodes": "nodes",
                                    "links": "links"
                                }
                            ]
                        }
                    },
                    "marks": [
                        {
                            "type": "path",
                            "from": {"data": "sankey"},
                            "clip": True,
                            "encode": {
                                "enter": {
                                    "stroke": {"scale": "color", "field": "source.name"},
                                    "strokeWidth": {"field": "width"},
                                    "strokeOpacity": {"value": 0.5}
                                },
                                "update": {
                                    "path": {"field": "path"}
                                }
                            }
                        }
                    ]
                },
                {
                    "type": "rect",
                    "from": {"data": "nodes"},
                    "encode": {
                        "enter": {
                            "x": {"field": "x0"},
                            "x2": {"field": "x1"},
                            "y": {"field": "y0"},
                            "y2": {"field": "y1"},
                            "fill": {"scale": "color", "field": "name"},
                            "stroke": {"value": "#000"},
                            "strokeWidth": {"value": 0.5}
                        }
                    }
                },
                {
                    "type": "text",
                    "from": {"data": "nodes"},
                    "encode": {
                        "enter": {
                            "x": {"signal": "datum.x0 < width / 2 ? datum.x1 + 5 : datum.x0 - 5"},
                            "y": {"signal": "(datum.y0 + datum.y1) / 2"},
                            "align": {"signal": "datum.x0 < width / 2 ? 'left' : 'right'"},
                            "baseline": {"value": "middle"},
                            "text": {"field": "name"},
                            "fontSize": {"value": 10}
                        }
                    }
                }
            ]
        }
        
        return spec
    
    def save_spec(self, spec: Dict[str, Any], output_path: str) -> str:
        """
        JSON
        
        Args:
            spec: Vega/Vega-Lite
            output_path: 
        
        Returns:
            
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)
        
        return str(output_path)


def convert_csv_to_vega(
    csv_path: str,
    chart_type: ChartType,
    output_path: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    ：CSVVega/Vega-Lite
    
    Args:
        csv_path: CSV
        chart_type:  ("scatter", "bar", "line", "parallel", "heatmap", "sankey")
        output_path: JSON（）
        **kwargs: convert
    
    Returns:
        Vega/Vega-Lite
    """
    converter = VegaConverter(csv_path)
    spec = converter.convert(chart_type, **kwargs)
    
    if output_path:
        converter.save_spec(spec, output_path)
    
    return spec


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CSV to Vega/Vega-Lite Converter")
    parser.add_argument("csv_path", help="CSV")
    parser.add_argument("chart_type", choices=["scatter", "bar", "line", "parallel", "heatmap", "sankey"],
                       help="")
    parser.add_argument("-o", "--output", help="JSON")
    parser.add_argument("--x", help="X")
    parser.add_argument("--y", help="Y")
    parser.add_argument("--color", help="")
    parser.add_argument("--size", help="（）")
    parser.add_argument("--columns", nargs="+", help="")
    parser.add_argument("--normalize", action="store_true", help="（）")
    parser.add_argument("--source", help="")
    parser.add_argument("--target", help="")
    parser.add_argument("--value", help="")
    parser.add_argument("--title", help="")
    parser.add_argument("--width", type=int, default=600, help="")
    parser.add_argument("--height", type=int, default=400, help="")
    
    args = parser.parse_args()
    
    spec = convert_csv_to_vega(
        csv_path=args.csv_path,
        chart_type=args.chart_type,
        output_path=args.output,
        x=args.x,
        y=args.y,
        color=args.color,
        size=args.size,
        columns=args.columns,
        normalize=args.normalize,
        source=args.source,
        target=args.target,
        value=args.value,
        title=args.title,
        width=args.width,
        height=args.height
    )
    
    if not args.output:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
