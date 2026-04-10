"""
（ -  state）
"""

from typing import Dict, Any, List, Optional, Union, Tuple
import copy
import json
from datetime import datetime
from state_manager import DataStore, tool_output


def _datum_ref(field: str) -> str:
    """Vega expr: datum access for field names with spaces/special chars."""
    if not field:
        return "datum"
    s = str(field).replace("\\", "\\\\").replace("'", "\\'")
    return f"datum['{s}']"


def adjust_color_scale(state: Dict, scheme: str = "viridis", domain: List = None) -> Dict[str, Any]:
    """
    
    
    Args:
        state: Vega-Lite
        scheme:  ( "viridis", "blues", "reds", "greens", "oranges", "purples")
        domain:  [min, max]，
    """
    new_state = copy.deepcopy(state)
    
    if 'encoding' not in new_state:
        new_state['encoding'] = {}
    if 'color' not in new_state['encoding']:
        new_state['encoding']['color'] = {}
    if 'scale' not in new_state['encoding']['color']:
        new_state['encoding']['color']['scale'] = {}
    
    # 
    new_state['encoding']['color']['scale']['scheme'] = scheme
    
    #  domain，
    if domain is not None and len(domain) == 2:
        new_state['encoding']['color']['scale']['domain'] = domain
    
    message = f'Changed color scheme to {scheme}'
    if domain:
        message += f' with domain [{domain[0]}, {domain[1]}]'
    
    return {
        'success': True,
        'operation': 'adjust_color_scale',
        'vega_state': new_state,
        'message': message
    }


def filter_cells(
    state: Dict,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Dict[str, Any]:
    """
    。
    ： min_value  >= min ， max_value  <= max ， [min, max] 。
    """
    if min_value is None and max_value is None:
        return {'success': False, 'error': 'Must provide at least one of min_value or max_value'}

    new_state = copy.deepcopy(state)

    color_enc = (new_state.get('encoding', {}) or {}).get('color', {}) or {}
    color_field = color_enc.get('field')
    if not color_field:
        return {'success': False, 'error': 'Cannot find color field'}

    # Transform filters apply to input rows before encoding aggregation. Using a synthetic
    # name like mean_Total_Bill_Amount does not exist on raw rows and would drop all cells.
    value_field = color_field

    if 'transform' not in new_state:
        new_state['transform'] = []

    ref = _datum_ref(value_field)
    tests: List[str] = []
    if min_value is not None:
        tests.append(f'{ref} >= {float(min_value)}')
    if max_value is not None:
        tests.append(f'{ref} <= {float(max_value)}')
    filter_expr = ' && '.join(tests)

    new_state['transform'].append({'filter': filter_expr})

    msg = 'Filtered cells'
    if min_value is not None and max_value is not None:
        msg = f'Filtered cells to [{min_value}, {max_value}]'
    elif min_value is not None:
        msg = f'Filtered cells to >= {min_value}'
    else:
        msg = f'Filtered cells to <= {max_value}'

    return {
        'success': True,
        'operation': 'filter_cells',
        'vega_state': new_state,
        'message': msg
    }

def highlight_region(
    state: Dict,
    x_values: Optional[List] = None,
    y_values: Optional[List] = None,
) -> Dict[str, Any]:
    """
    。x_values  y_values ：
    -  x_values：（ x  y）
    -  y_values：（ y  x）
    - ：
    """
    new_state = copy.deepcopy(state)
    
    x_field = new_state.get('encoding', {}).get('x', {}).get('field')
    y_field = new_state.get('encoding', {}).get('y', {}).get('field')
    x_timeunit = new_state.get('encoding', {}).get('x', {}).get('timeUnit')
    y_timeunit = new_state.get('encoding', {}).get('y', {}).get('timeUnit')
    
    if not x_field or not y_field:
        return {'success': False, 'error': 'Cannot find x/y fields'}

    x_vals = x_values if x_values is not None else []
    y_vals = y_values if y_values is not None else []
    if not x_vals and not y_vals:
        return {'success': False, 'error': 'Must provide at least one of x_values or y_values'}

    # Month name map (Vega month(): 0=Jan ... 11=Dec)
    MONTH_MAP = {
        "Jan": 0, "Feb": 1, "Mar": 2, "Apr": 3, "May": 4, "Jun": 5,
        "Jul": 6, "Aug": 7, "Sep": 8, "Oct": 9, "Nov": 10, "Dec": 11,
        "January": 0, "February": 1, "March": 2, "April": 3, "June": 5,
        "July": 6, "August": 7, "September": 8, "October": 9, "November": 10, "December": 11
    }

    def _normalize_values_for_timeunit(field_name: str, values: List, timeunit: Optional[str]) -> Tuple[str, str]:
        """
        Returns (value_list_str, expr) where expr is the datum-side expression to test.
        value_list_str is already formatted for use inside [ ... ].
        """
        if not timeunit:
            # Treat as raw field value (string compare)
            value_list_str = ','.join([f'"{v}"' for v in values])
            return value_list_str, f'datum["{field_name}"]'

        tu = str(timeunit).lower().strip()
        if tu == 'date':
            nums = []
            for v in values:
                try:
                    nums.append(str(int(v)))
                except Exception:
                    pass
            value_list_str = ','.join(nums) if nums else ','.join([f'"{v}"' for v in values])
            return value_list_str, f'date(datum["{field_name}"])'
        if tu == 'month':
            months = []
            for v in values:
                if isinstance(v, str) and v in MONTH_MAP:
                    months.append(str(MONTH_MAP[v]))
                else:
                    try:
                        m = int(v)
                        # user-facing month is 1-12; vega month() is 0-11
                        months.append(str(m - 1))
                    except Exception:
                        pass
            value_list_str = ','.join(months) if months else ','.join([f'"{v}"' for v in values])
            return value_list_str, f'month(datum["{field_name}"])'
        if tu == 'year':
            years = []
            for v in values:
                try:
                    years.append(str(int(v)))
                except Exception:
                    pass
            value_list_str = ','.join(years) if years else ','.join([f'"{v}"' for v in values])
            return value_list_str, f'year(datum["{field_name}"])'

        # other timeUnit fall back
        value_list_str = ','.join([f'"{v}"' for v in values])
        return value_list_str, f'{tu}(datum["{field_name}"])'

    # Build expressions for x/y (support temporal+timeUnit); only for axes with values
    parts: List[str] = []
    if x_vals:
        x_list, x_expr = _normalize_values_for_timeunit(x_field, x_vals, x_timeunit)
        parts.append(f'indexof([{x_list}], {x_expr}) >= 0')
    if y_vals:
        y_list, y_expr = _normalize_values_for_timeunit(y_field, y_vals, y_timeunit)
        parts.append(f'indexof([{y_list}], {y_expr}) >= 0')
    test_expr = ' && '.join(parts)
    
    if 'encoding' not in new_state:
        new_state['encoding'] = {}
    
    new_state['encoding']['opacity'] = {
        'condition': {
            'test': test_expr,
            'value': 1.0
        },
        # ，
        'value': 0.15
    }
    
    return {
        'success': True,
        'operation': 'highlight_region',
        'vega_state': new_state,
        'message': 'Highlighted specified region'
    }


def highlight_region_by_value(
    state: Dict,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    outside_opacity: float = 0.12,
) -> Dict[str, Any]:
    """
    “”（ color /）：，；。

    ：
    - ， transform.filter，。
    - ： min_value  max_value。
    """
    if min_value is None and max_value is None:
        return {'success': False, 'error': 'Must provide at least one of min_value or max_value'}

    new_state = copy.deepcopy(state)

    color_enc = (new_state.get('encoding', {}) or {}).get('color', {}) or {}
    color_field = color_enc.get('field')
    if not color_field:
        return {'success': False, 'error': 'Cannot find color field'}

    # If color uses aggregation, Vega-Lite datum field is typically "<op>_<field>" unless "as" is set.
    agg = color_enc.get('aggregate')
    agg_as = color_enc.get('as')
    value_field = color_field
    if agg:
        if isinstance(agg_as, str) and agg_as.strip():
            value_field = agg_as.strip()
        else:
            value_field = f'{str(agg).lower()}_{color_field}'

    ref = _datum_ref(value_field)
    tests: List[str] = []
    if min_value is not None:
        tests.append(f'{ref} >= {float(min_value)}')
    if max_value is not None:
        tests.append(f'{ref} <= {float(max_value)}')
    test_expr = ' && '.join(tests) if tests else 'true'

    if 'encoding' not in new_state:
        new_state['encoding'] = {}
    new_state['encoding']['opacity'] = {
        'condition': {
            'test': test_expr,
            'value': 1.0
        },
        'value': float(outside_opacity)
    }

    return {
        'success': True,
        'operation': 'highlight_region_by_value',
        'vega_state': new_state,
        'message': f'Highlighted cells by value (min={min_value}, max={max_value}); outside_opacity={outside_opacity}'
    }


def filter_cells_by_region(
    state: Dict,
    x_value: Any = None,
    y_value: Any = None,
    x_values: Optional[List[Any]] = None,
    y_values: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    （x/y）（ transform.filter ）。
    x  y ：
    -  x： x 
    -  y： y 
    - ：

    ：
    - ： x_value + y_value
    - （）： x_values + y_values
    """
    new_state = copy.deepcopy(state)

    x_field = (new_state.get('encoding', {}) or {}).get('x', {}).get('field')
    y_field = (new_state.get('encoding', {}) or {}).get('y', {}).get('field')
    x_timeunit = (new_state.get('encoding', {}) or {}).get('x', {}).get('timeUnit')
    y_timeunit = (new_state.get('encoding', {}) or {}).get('y', {}).get('timeUnit')
    if not x_field or not y_field:
        return {'success': False, 'error': 'Cannot find x/y fields'}

    # normalize to lists
    if x_values is None and x_value is not None:
        x_values = [x_value]
    if y_values is None and y_value is not None:
        y_values = [y_value]
    if (not x_values or len(x_values) == 0) and (not y_values or len(y_values) == 0):
        return {'success': False, 'error': 'Must provide at least one of x_value/x_values or y_value/y_values'}

    # Reuse the same normalization logic as highlight_region for timeUnit (month/year/date)
    MONTH_MAP = {
        "Jan": 0, "Feb": 1, "Mar": 2, "Apr": 3, "May": 4, "Jun": 5,
        "Jul": 6, "Aug": 7, "Sep": 8, "Oct": 9, "Nov": 10, "Dec": 11,
        "January": 0, "February": 1, "March": 2, "April": 3, "June": 5,
        "July": 6, "August": 7, "September": 8, "October": 9, "November": 10, "December": 11
    }

    def _normalize_values_for_timeunit(field_name: str, values: List[Any], timeunit: Optional[str]) -> Tuple[str, str]:
        if not timeunit:
            value_list_str = ','.join([json.dumps(v, ensure_ascii=False) for v in values])
            return value_list_str, _datum_ref(field_name)

        tu = str(timeunit).lower().strip()
        if tu == 'date':
            nums = []
            for v in values:
                try:
                    nums.append(str(int(v)))
                except Exception:
                    pass
            value_list_str = ','.join(nums) if nums else ','.join([json.dumps(v, ensure_ascii=False) for v in values])
            return value_list_str, f'date({_datum_ref(field_name)})'
        if tu == 'month':
            months = []
            for v in values:
                if isinstance(v, str) and v in MONTH_MAP:
                    months.append(str(MONTH_MAP[v]))
                else:
                    try:
                        m = int(v)
                        months.append(str(m - 1))
                    except Exception:
                        pass
            value_list_str = ','.join(months) if months else ','.join([json.dumps(v, ensure_ascii=False) for v in values])
            return value_list_str, f'month({_datum_ref(field_name)})'
        if tu == 'year':
            years = []
            for v in values:
                try:
                    years.append(str(int(v)))
                except Exception:
                    pass
            value_list_str = ','.join(years) if years else ','.join([json.dumps(v, ensure_ascii=False) for v in values])
            return value_list_str, f'year({_datum_ref(field_name)})'

        value_list_str = ','.join([json.dumps(v, ensure_ascii=False) for v in values])
        return value_list_str, f'{tu}({_datum_ref(field_name)})'

    exclude_parts: List[str] = []
    if x_values and len(x_values) > 0:
        x_list, x_expr = _normalize_values_for_timeunit(x_field, list(x_values), x_timeunit)
        exclude_parts.append(f'indexof([{x_list}], {x_expr}) >= 0')
    if y_values and len(y_values) > 0:
        y_list, y_expr = _normalize_values_for_timeunit(y_field, list(y_values), y_timeunit)
        exclude_parts.append(f'indexof([{y_list}], {y_expr}) >= 0')
    exclude_expr = ' && '.join(exclude_parts)

    if 'transform' not in new_state:
        new_state['transform'] = []
    new_state['transform'].append({'filter': f'!({exclude_expr})', '_avs_tag': 'filter_cells_by_region'})

    return {
        'success': True,
        'operation': 'filter_cells_by_region',
        'vega_state': new_state,
        'message': f'Filtered out selected region cells (x={x_values}, y={y_values})'
    }


def cluster_rows_cols(state: Dict, cluster_rows: bool = True, 
                     cluster_cols: bool = True, method: str = "sum") -> Dict[str, Any]:
    """
    /（）
    
    ：
    -  encoding.color.field （）。
    - （Y ）： color （sum/mean/max）；
      （X ）： color 。
    -  encoding.y.sort / encoding.x.sort  { op, field, order } ，
      Vega-Lite  op  field ，/，。
    
    ：“/”，；，。
    """
    new_state = copy.deepcopy(state)
    
    if 'encoding' not in new_state:
        return {'success': False, 'error': 'No encoding found'}
    
    encoding = new_state['encoding']
    color_field = encoding.get('color', {}).get('field')
    
    if not color_field:
        return {'success': False, 'error': 'Cannot find color field for sorting'}
    
    if method == "sum":
        sort_op = "sum"
    elif method == "mean":
        sort_op = "mean"
    elif method == "max":
        sort_op = "max"
    else:
        sort_op = "sum"
    
    if cluster_rows and 'y' in encoding:
        encoding['y']['sort'] = {
            'op': sort_op,
            'field': color_field,
            'order': 'descending'
        }
    
    if cluster_cols and 'x' in encoding:
        encoding['x']['sort'] = {
            'op': sort_op,
            'field': color_field,
            'order': 'descending'
        }
    
    return {
        'success': True,
        'operation': 'cluster_rows_cols',
        'vega_state': new_state,
        'message': f'Sorted rows={cluster_rows}, cols={cluster_cols} by {method}'
    }


def select_submatrix(state: Dict, x_values: List = None, 
                    y_values: List = None) -> Dict[str, Any]:
    """Select a submatrix of the heatmap."""
    if not x_values and not y_values:
        return {'success': False, 'error': 'Must specify x_values or y_values'}
    
    new_state = copy.deepcopy(state)
    
    #  (Vega month  0 : 0=Jan, 11=Dec)
    MONTH_MAP = {
        "Jan": 0, "Feb": 1, "Mar": 2, "Apr": 3,
        "May": 4, "Jun": 5, "Jul": 6, "Aug": 7,
        "Sep": 8, "Oct": 9, "Nov": 10, "Dec": 11,
        "January": 0, "February": 1, "March": 2, "April": 3,
        "May": 4, "June": 5, "July": 6, "August": 7,
        "September": 8, "October": 9, "November": 10, "December": 11
    }
    
    encoding = new_state.get('encoding', {})
    x_encoding = encoding.get('x', {})
    y_encoding = encoding.get('y', {})
    
    x_field = x_encoding.get('field')
    y_field = y_encoding.get('field')
    x_timeunit = x_encoding.get('timeUnit')
    y_timeunit = y_encoding.get('timeUnit')
    
    if 'transform' not in new_state:
        new_state['transform'] = []
    
    filters = []
    
    #  X 
    if x_values and x_field:
        if x_timeunit:
            #  timeUnit， Vega 
            if x_timeunit == 'date':
                # （1-31）
                x_nums = ','.join([str(int(v)) for v in x_values])
                filters.append(f'indexof([{x_nums}], date(datum.{x_field})) >= 0')
            elif x_timeunit == 'month':
                # ，
                x_months = []
                for v in x_values:
                    if v in MONTH_MAP:
                        x_months.append(str(MONTH_MAP[v]))
                    else:
                        try:
                            x_months.append(str(int(v)))
                        except:
                            x_months.append(f'"{v}"')
                x_str = ','.join(x_months)
                filters.append(f'indexof([{x_str}], month(datum.{x_field})) >= 0')
            elif x_timeunit == 'year':
                x_nums = ','.join([str(int(v)) for v in x_values])
                filters.append(f'indexof([{x_nums}], year(datum.{x_field})) >= 0')
            else:
                #  timeUnit，
                x_str = ','.join([f'"{v}"' for v in x_values])
                filters.append(f'indexof([{x_str}], {x_timeunit}(datum.{x_field})) >= 0')
        else:
            #  timeUnit，
            x_str = ','.join([f'"{v}"' for v in x_values])
            filters.append(f'indexof([{x_str}], datum.{x_field}) >= 0')
    
    #  Y 
    if y_values and y_field:
        if y_timeunit:
            #  timeUnit， Vega 
            if y_timeunit == 'date':
                y_nums = ','.join([str(int(v)) for v in y_values])
                filters.append(f'indexof([{y_nums}], date(datum.{y_field})) >= 0')
            elif y_timeunit == 'month':
                # ，
                y_months = []
                for v in y_values:
                    if v in MONTH_MAP:
                        y_months.append(str(MONTH_MAP[v]))
                    else:
                        try:
                            y_months.append(str(int(v)))
                        except:
                            y_months.append(f'"{v}"')
                y_str = ','.join(y_months)
                filters.append(f'indexof([{y_str}], month(datum.{y_field})) >= 0')
            elif y_timeunit == 'year':
                y_nums = ','.join([str(int(v)) for v in y_values])
                filters.append(f'indexof([{y_nums}], year(datum.{y_field})) >= 0')
            else:
                #  timeUnit，
                y_str = ','.join([f'"{v}"' for v in y_values])
                filters.append(f'indexof([{y_str}], {y_timeunit}(datum.{y_field})) >= 0')
        else:
            #  timeUnit，
            y_str = ','.join([f'"{v}"' for v in y_values])
            filters.append(f'indexof([{y_str}], datum.{y_field}) >= 0')
    
    if filters:
        new_state['transform'].append({
            'filter': ' && '.join(filters)
        })
    
    return {
        'success': True,
        'operation': 'select_submatrix',
        'vega_state': new_state,
        'message': f'Selected submatrix with {len(x_values) if x_values else "all"} cols, {len(y_values) if y_values else "all"} rows'
    }


def find_extremes(state: Dict, top_n: int = 5, mode: str = "both") -> Dict[str, Any]:
    """
    
    
    Args:
        state: Vega-Lite
        top_n: N
        mode: "max" | "min" | "both"
    """
    new_state = copy.deepcopy(state)
    
    # 
    encoding = new_state.get('encoding', {})
    x_field = encoding.get('x', {}).get('field')
    y_field = encoding.get('y', {}).get('field')
    color_field = encoding.get('color', {}).get('field')
    
    if not color_field:
        return {'success': False, 'error': 'Cannot find color field for finding extremes'}
    
    # 
    data = _get_data_values(new_state)
    if not data:
        return {'success': False, 'error': 'No data found'}
    
    # （ x/y ）
    agg_op = (encoding.get('color', {}) or {}).get('aggregate')
    agg_op = str(agg_op).lower().strip() if agg_op else 'mean'
    allowed = {"mean", "sum", "max", "min", "median", "count"}
    if agg_op not in allowed:
        agg_op = 'mean'
    
    grouped = {}
    for d in data:
        if d.get(color_field) is None:
            continue
        x_val = d.get(x_field)
        y_val = d.get(y_field)
        if x_val is None or y_val is None:
            continue
        key = (x_val, y_val)
        grouped.setdefault(key, []).append(d.get(color_field))
    
    def _aggregate(vals: List[Any]) -> float:
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums:
            return 0.0
        if agg_op == 'sum':
            return float(sum(nums))
        if agg_op == 'max':
            return float(max(nums))
        if agg_op == 'min':
            return float(min(nums))
        if agg_op == 'median':
            s = sorted(nums)
            mid = len(s) // 2
            return float(s[mid]) if len(s) % 2 == 1 else float((s[mid - 1] + s[mid]) / 2)
        if agg_op == 'count':
            return float(len(nums))
        # mean (default)
        return float(sum(nums) / len(nums))
    
    aggregated = [
        {x_field: k[0], y_field: k[1], color_field: _aggregate(v)}
        for k, v in grouped.items()
    ]
    if not aggregated:
        return {'success': False, 'error': 'No aggregated values found'}
    
    # 
    sorted_data = sorted(
        aggregated,
        key=lambda x: x.get(color_field, 0)
    )
    
    extremes = []
    if mode in ["max", "both"]:
        extremes.extend(sorted_data[-top_n:])
    if mode in ["min", "both"]:
        extremes.extend(sorted_data[:top_n])
    
    # （）
    dx, dy = _datum_ref(x_field), _datum_ref(y_field)
    extreme_conditions = []
    for e in extremes:
        x_val = e.get(x_field)
        y_val = e.get(y_field)
        if x_val is not None and y_val is not None:
            xq = json.dumps(x_val) if isinstance(x_val, str) else x_val
            yq = json.dumps(y_val) if isinstance(y_val, str) else y_val
            extreme_conditions.append(f'({dx} === {xq} && {dy} === {yq})')
    
    if not extreme_conditions:
        return {'success': False, 'error': 'No extreme values found'}
    
    test_expr = ' || '.join(extreme_conditions)
    #  transparent  null， Vega 
    new_state['encoding']['stroke'] = {
        'condition': {'test': test_expr, 'value': 'red'},
        'value': 'transparent'
    }
    new_state['encoding']['strokeWidth'] = {
        'condition': {
            'test': test_expr,
            'value': 3
        },
        'value': 0
    }
    
    # 
    extreme_info = []
    for e in extremes:
        extreme_info.append({
            'x': e.get(x_field),
            'y': e.get(y_field),
            'value': e.get(color_field),
            'aggregate': agg_op
        })
    
    return {
        'success': True,
        'operation': 'find_extremes',
        'vega_state': new_state,
        'extremes': extreme_info,
        'message': f'Marked {len(extremes)} extreme points (mode: {mode})'
    }


def threshold_mask(
    state: Dict,
    min_value: float,
    max_value: float,
    outside_opacity: float = 0.1,
) -> Dict[str, Any]:
    """
    “”（），。
    
    Args:
        state: Vega-Lite
        min_value: （）
        max_value: （）
        outside_opacity: 
    """
    new_state = copy.deepcopy(state)

    color_enc = new_state.get('encoding', {}).get('color', {})
    color_field = color_enc.get('field')
    if not color_field:
        return {'success': False, 'error': 'Cannot find color field'}

    # If color uses aggregation, the datum field is typically "<op>_<field>" unless "as" is set.
    agg = color_enc.get('aggregate')
    agg_as = color_enc.get('as')
    value_field = color_field
    if agg:
        if isinstance(agg_as, str) and agg_as.strip():
            value_field = agg_as.strip()
        else:
            value_field = f'{str(agg).lower()}_{color_field}'

    if 'encoding' not in new_state:
        new_state['encoding'] = {}

    ref = _datum_ref(value_field)
    new_state['encoding']['opacity'] = {
        'condition': {
            'test': f'{ref} >= {min_value} && {ref} <= {max_value}',
            'value': 1.0
        },
        'value': float(outside_opacity)
    }

    return {
        'success': True,
        'operation': 'threshold_mask',
        'vega_state': new_state,
        'message': f'Applied threshold mask on {value_field} in [{min_value}, {max_value}]'
    }


def drilldown_axis(
    state: Dict,
    level: str,
    value: Union[int, str],
    parent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    ： ->  -> 
    
    ：
    -  encoding.x.field， encoding.x.type == 'temporal'
    -  timeUnit='year'（， reset ）
    
    Args:
        state: Vega-Lite
        level: 'year' | 'month' | 'date'
        value:  level （year=int；month=1-12；date=1-31）
        parent: ， {'year': 2012}  {'year':2012,'month':3}
    """
    new_state = copy.deepcopy(state)

    encoding = new_state.get('encoding', {})
    x_enc = encoding.get('x', {})
    time_field = x_enc.get('field')
    x_type = x_enc.get('type')

    if not time_field:
        return {'success': False, 'error': 'Cannot find temporal x field for drilldown'}
    if x_type and x_type != 'temporal':
        return {'success': False, 'error': f'Expected encoding.x.type=temporal, got {x_type}'}

    # init state
    state = new_state.get('_heatmap_state')
    if not isinstance(state, dict):
        state = {}

    if 'original_x_encoding' not in state:
        state['original_x_encoding'] = copy.deepcopy(x_enc)

    if 'transform' not in new_state:
        new_state['transform'] = []

    # remove existing drilldown filters (idempotent drilldown)
    new_state['transform'] = [
        t for t in new_state['transform']
        if not (isinstance(t, dict) and t.get('_avs_tag') == 'heatmap_drilldown_axis')
    ]

    # parent merge (explicit parent > stored state)
    p = {}
    if isinstance(state.get('parent'), dict):
        p.update(state.get('parent'))
    if isinstance(parent, dict):
        p.update(parent)

    # normalize level
    level = str(level).lower().strip()

    # build filter + new timeUnit
    filters: List[str] = []
    next_timeunit: Optional[str] = None

    if level == 'year':
        try:
            year_val = int(value)
        except Exception:
            return {'success': False, 'error': f'Invalid year value: {value}'}

        state['parent'] = {'year': year_val}
        next_timeunit = 'month'
        filters.append(f'year(datum.{time_field}) == {year_val}')

    elif level == 'month':
        # month drilldown needs year
        year_val = p.get('year')
        if year_val is None:
            return {'success': False, 'error': 'Month drilldown requires parent.year'}
        try:
            year_val = int(year_val)
            month_val = int(value)
        except Exception:
            return {'success': False, 'error': f'Invalid month drilldown values: year={year_val}, month={value}'}

        state['parent'] = {'year': year_val, 'month': month_val}
        next_timeunit = 'date'
        # Vega-Lite month() returns 0-11, so month 1-12 => compare month()==month-1
        filters.append(f'year(datum.{time_field}) == {year_val}')
        filters.append(f'month(datum.{time_field}) == {month_val - 1}')

    elif level == 'date':
        # date drilldown needs year+month
        year_val = p.get('year')
        month_val = p.get('month')
        if year_val is None or month_val is None:
            return {'success': False, 'error': 'Date drilldown requires parent.year and parent.month'}
        try:
            year_val = int(year_val)
            month_val = int(month_val)
            date_val = int(value)
        except Exception:
            return {'success': False, 'error': f'Invalid date drilldown values: {p}, date={value}'}

        state['parent'] = {'year': year_val, 'month': month_val, 'date': date_val}
        next_timeunit = 'date'
        filters.append(f'year(datum.{time_field}) == {year_val}')
        filters.append(f'month(datum.{time_field}) == {month_val - 1}')
        filters.append(f'date(datum.{time_field}) == {date_val}')

    else:
        return {'success': False, 'error': f'Unsupported level: {level}. Use year|month|date'}

    # apply timeUnit on x
    if 'encoding' not in new_state:
        new_state['encoding'] = {}
    if 'x' not in new_state['encoding']:
        new_state['encoding']['x'] = {}
    if next_timeunit:
        new_state['encoding']['x']['timeUnit'] = next_timeunit
        new_state['encoding']['x']['type'] = 'temporal'
        new_state['encoding']['x']['field'] = time_field

    # add filter transform
    if filters:
        new_state['transform'].append({
            'filter': ' && '.join(filters),
            '_avs_tag': 'heatmap_drilldown_axis'
        })

    new_state['_heatmap_state'] = state

    return {
        'success': True,
        'operation': 'drilldown_axis',
        'vega_state': new_state,
        'message': f'Drilldown to {level}={value}',
        'state': state.get('parent')
    }


def reset_drilldown(state: Dict) -> Dict[str, Any]:
    """
    ： drilldown_axis  filter， x （timeUnit ）。
    """
    new_state = copy.deepcopy(state)

    state = new_state.get('_heatmap_state')
    original_x = None
    if isinstance(state, dict):
        original_x = state.get('original_x_encoding')

    if 'transform' in new_state and isinstance(new_state['transform'], list):
        new_state['transform'] = [
            t for t in new_state['transform']
            if not (isinstance(t, dict) and t.get('_avs_tag') == 'heatmap_drilldown_axis')
        ]

    if original_x and isinstance(original_x, dict):
        if 'encoding' not in new_state:
            new_state['encoding'] = {}
        new_state['encoding']['x'] = copy.deepcopy(original_x)

    # clear state
    if '_heatmap_state' in new_state:
        del new_state['_heatmap_state']

    return {
        'success': True,
        'operation': 'reset_drilldown',
        'vega_state': new_state,
        'message': 'Reset heatmap drilldown to original state'
    }


# ============================================================================
# Marginal bars (interaction necessity)
# - Add top (column) and right (row) marginal bar charts to a heatmap
# - Default aggregation: mean (as requested)
# ============================================================================

def add_marginal_bars(
    state: Dict,
    op: str = "mean",
    show_top: bool = True,
    show_right: bool = True,
    bar_size: int = 70,
    bar_color: str = "#666666",
) -> Dict[str, Any]:
    """
    （/），（mean）。

    ：
    -  data、transform、config； encoding.x / encoding.y、encoding.color  x 、y 、。
    - ： x ， color  op （mean/sum/median ），； x （vconcat + resolve scale x shared）。
    - ： y ， color  op ，； y （hconcat + resolve scale y shared）。
    -  spec  width/height， 400×300， concat 。

    ：“/”；/， mean。
    """
    if not show_top and not show_right:
        return {'success': False, 'error': 'At least one of show_top/show_right must be True'}

    new_state = copy.deepcopy(state)
    encoding = new_state.get("encoding", {}) or {}
    x_enc = encoding.get("x", {}) or {}
    y_enc = encoding.get("y", {}) or {}
    c_enc = encoding.get("color", {}) or {}

    x_field = x_enc.get("field")
    y_field = y_enc.get("field")
    value_field = c_enc.get("field")
    if not x_field or not y_field or not value_field:
        return {'success': False, 'error': 'Cannot find required fields in encoding.x/encoding.y/encoding.color'}

    agg = str(op).lower().strip()
    allowed = {"mean", "sum", "median", "max", "min", "count"}
    if agg not in allowed:
        return {'success': False, 'error': f'Unsupported op: {op}. Use one of {sorted(list(allowed))}'}

    main = copy.deepcopy(new_state)
    title = main.pop("title", None)

    default_w, default_h = 400, 300
    mw = main.get("width") if isinstance(main.get("width"), (int, float)) else None
    mh = main.get("height") if isinstance(main.get("height"), (int, float)) else None
    if mw is None:
        main["width"] = default_w
        mw = default_w
    if mh is None:
        main["height"] = default_h
        mh = default_h

    base_data = main.get("data")
    base_transform = main.get("transform")
    base_config = main.get("config")

    def _base_block() -> Dict[str, Any]:
        block: Dict[str, Any] = {}
        if base_data is not None:
            block["data"] = copy.deepcopy(base_data)
        if base_transform is not None:
            block["transform"] = copy.deepcopy(base_transform)
        if base_config is not None:
            block["config"] = copy.deepcopy(base_config)
        return block

    top_spec = None
    if show_top:
        top_spec = {
            **_base_block(),
            "mark": {"type": "bar", "color": bar_color},
            "encoding": {
                "x": copy.deepcopy(x_enc),
                "y": {"aggregate": agg, "field": value_field, "type": "quantitative", "title": None},
                "tooltip": [
                    {"field": x_field, **({"timeUnit": x_enc.get("timeUnit")} if x_enc.get("timeUnit") else {}), "type": x_enc.get("type", "nominal"), "title": x_enc.get("title", x_field)},
                    {"aggregate": agg, "field": value_field, "type": "quantitative", "title": f"{agg}({value_field})"},
                ],
            },
            "height": int(bar_size),
            "width": int(mw),
        }
        top_spec["encoding"]["x"]["axis"] = {"labels": False, "ticks": False, "title": None, "domain": False}
        top_spec["encoding"]["y"]["axis"] = {"grid": False, "ticks": False, "title": None}

    right_spec = None
    if show_right:
        right_spec = {
            **_base_block(),
            "mark": {"type": "bar", "color": bar_color},
            "encoding": {
                "y": copy.deepcopy(y_enc),
                "x": {"aggregate": agg, "field": value_field, "type": "quantitative", "title": None},
                "tooltip": [
                    {"field": y_field, **({"timeUnit": y_enc.get("timeUnit")} if y_enc.get("timeUnit") else {}), "type": y_enc.get("type", "nominal"), "title": y_enc.get("title", y_field)},
                    {"aggregate": agg, "field": value_field, "type": "quantitative", "title": f"{agg}({value_field})"},
                ],
            },
            "width": int(bar_size),
            "height": int(mh),
        }
        right_spec["encoding"]["y"]["axis"] = {"labels": False, "ticks": False, "title": None, "domain": False}
        right_spec["encoding"]["x"]["axis"] = {"grid": False, "ticks": False, "title": None}

    # Compose: vconcat(top, hconcat(main, right))
    # We want x shared between top and main; y shared between main and right.
    row = {
        "hconcat": [main] + ([right_spec] if right_spec else []),
        "resolve": {"scale": {"y": "shared"}},
    }
    composed: Dict[str, Any] = {
        "$schema": new_state.get("$schema", "https://vega.github.io/schema/vega-lite/v5.json"),
        "vconcat": ([] if not top_spec else [top_spec]) + [row],
        "resolve": {"scale": {"x": "shared"}},
    }
    if title is not None:
        composed["title"] = title

    composed["_marginal_bars_state"] = {
        "enabled": True,
        "op": agg,
        "show_top": bool(show_top),
        "show_right": bool(show_right),
        "value_field": value_field,
        "x_field": x_field,
        "y_field": y_field,
        "updated_at": datetime.now().isoformat(),
    }

    return {
        "success": True,
        "operation": "add_marginal_bars",
        "vega_state": composed,
        "message": f"Added marginal bars (op={agg}, top={show_top}, right={show_right})"
    }


def transpose(state: Dict) -> Dict[str, Any]:
    """Swap heatmap x and y encodings (transpose rows/columns)."""
    new_state = copy.deepcopy(state)
    
    encoding = new_state.get('encoding', {})
    x_enc = encoding.get('x')
    y_enc = encoding.get('y')
    
    if not x_enc or not y_enc:
        return {
            'success': False,
            'error': 'Cannot find both x and y encoding for transpose'
        }
    
    #  x  y 
    new_state['encoding']['x'] = copy.deepcopy(y_enc)
    new_state['encoding']['y'] = copy.deepcopy(x_enc)
    
    #  width  height（）
    width = new_state.get('width')
    height = new_state.get('height')
    if width is not None and height is not None:
        new_state['width'] = height
        new_state['height'] = width
    
    # （）
    state = new_state.get('_transpose_state', {'transposed': False})
    state['transposed'] = not state.get('transposed', False)
    new_state['_transpose_state'] = state
    
    status = "transposed" if state['transposed'] else "restored"
    return {
        'success': True,
        'operation': 'transpose',
        'vega_state': new_state,
        'message': f'Heatmap {status}: x and y axes swapped'
    }


def change_encoding(state: Dict, channel: str, field: str, type: Optional[str] = None) -> Dict[str, Any]:
    """
    Modify the field mapping of the specified encoding channel
    
    Args:
        state: Vega spec
        
        channel: encoding channel ("x", "y", "color", "size", "shape")
        field: new field name
    """
    new_state = copy.deepcopy(state)
    


    # （）
    data = _get_data_values(new_state)
    resolved_field = field
    if data:
        available_fields = list(data[0].keys())
        if field not in data[0]:
            lowered = str(field).strip().lower()
            for candidate in available_fields:
                if str(candidate).strip().lower() == lowered:
                    resolved_field = candidate
                    break
        if resolved_field not in data[0]:
            return {
                'success': False,
                'error': f'Field "{field}" not found in data. Available fields: {available_fields}'
            }
    
    #  type 
    valid_types = ('quantitative', 'nominal', 'ordinal', 'temporal')
    if type and type in valid_types:
        field_type = type
    else:
        field_type = 'nominal'
        if data:
            sample_value = data[0].get(resolved_field)
            if isinstance(sample_value, (int, float)):
                field_type = 'quantitative'
            elif isinstance(sample_value, str):
                if any(sep in sample_value for sep in ['-', '/', ':']):
                    field_type = 'temporal'
    
    #  encoding
    if 'encoding' not in new_state:
        new_state['encoding'] = {}
    
    new_state['encoding'][channel] = {
        'field': resolved_field,
        'type': field_type
    }
    
    # 
    if channel == 'color':
        new_state['encoding'][channel]['legend'] = {'title': resolved_field}
        if field_type == 'quantitative':
            new_state['encoding'][channel]['scale'] = {'scheme': 'viridis'}
    elif channel == 'size':
        if field_type == 'quantitative':
            new_state['encoding'][channel]['scale'] = {'range': [50, 500]}
    
    return {
        'success': True,
        'operation': 'change_encoding',
        'vega_state': new_state,
        'message': f'Changed {channel} encoding to field "{resolved_field}" (type: {field_type})'
    }


def _get_data_values(spec: Dict) -> List[Dict[str, Any]]:
    data_obj = spec.get("data")
    if isinstance(data_obj, dict) and isinstance(data_obj.get("values"), list):
        return data_obj["values"]
    values = DataStore.get_values()
    return values if isinstance(values, list) else []


__all__ = [
    'adjust_color_scale',
    'filter_cells',
    'filter_cells_by_region',
    'highlight_region',
    'highlight_region_by_value',
    'cluster_rows_cols',
    'select_submatrix',
    'find_extremes',
    'threshold_mask',
    'drilldown_axis',
    'reset_drilldown',
    'add_marginal_bars',
    'transpose',
    'change_encoding',
]

for _fn_name in __all__:
    _fn = globals().get(_fn_name)
    if callable(_fn):
        globals()[_fn_name] = tool_output(_fn)
