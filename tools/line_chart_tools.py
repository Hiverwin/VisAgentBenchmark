"""
（ -  state）
"""

from typing import List, Dict, Any, Tuple, Optional
import copy
import json
from state_manager import DataStore, tool_output


def _datum_ref(field: str) -> str:
    """Vega expr: datum access for field names with spaces/special chars."""
    if not field:
        return "datum"
    s = str(field).replace("\\", "\\\\").replace("'", "\\'")
    return f"datum['{s}']"


def _get_time_field(state: Dict) -> Optional[str]:
    """（ layer ）"""
    #  layer 
    if 'layer' in state and len(state['layer']) > 0:
        encoding = state['layer'][0].get('encoding', {})
    else:
        encoding = state.get('encoding', {})
    
    #  x ， y 
    x_encoding = encoding.get('x', {})
    y_encoding = encoding.get('y', {})
    
    if x_encoding.get('type') == 'temporal':
        return x_encoding.get('field')
    elif y_encoding.get('type') == 'temporal':
        return y_encoding.get('field')
    
    # ，（ x ）
    return x_encoding.get('field') or y_encoding.get('field')


def _get_data_values(spec: Dict) -> List[Dict[str, Any]]:
    data_obj = spec.get("data")
    if isinstance(data_obj, dict) and isinstance(data_obj.get("values"), list):
        return data_obj["values"]
    values = DataStore.get_values()
    return values if isinstance(values, list) else []


def zoom_x_region(state: Dict, start: str, end: str) -> Dict[str, Any]:
    """ - （）"""
    new_state = copy.deepcopy(state)
    
    # （ layer ）
    time_field = _get_time_field(new_state)
    
    if not time_field:
        return {
            'success': False,
            'error': 'Cannot find time field'
        }
    
    # 
    if 'layer' in new_state and len(new_state['layer']) > 0:
        encoding = new_state['layer'][0].get('encoding', {})
    else:
        encoding = new_state.get('encoding', {})
    
    x_field = encoding.get('x', {}).get('field')
    time_axis = 'x' if x_field == time_field else 'y'
    
    # VLM，
    # VLM
    if 'layer' in new_state and len(new_state['layer']) > 0:
        layer_encoding = new_state['layer'][0].get('encoding', {})
        if time_axis not in layer_encoding:
            layer_encoding[time_axis] = {}
        if 'scale' not in layer_encoding[time_axis]:
            layer_encoding[time_axis]['scale'] = {}
        layer_encoding[time_axis]['scale']['domain'] = [start, end]
    else:
        if 'encoding' not in new_state:
            new_state['encoding'] = {}
        if time_axis not in new_state['encoding']:
            new_state['encoding'][time_axis] = {}
        if 'scale' not in new_state['encoding'][time_axis]:
            new_state['encoding'][time_axis]['scale'] = {}
        new_state['encoding'][time_axis]['scale']['domain'] = [start, end]
    
    #  mark  clip: true，
    if 'layer' in new_state:
        for layer in new_state['layer']:
            if 'mark' in layer:
                if isinstance(layer['mark'], dict):
                    layer['mark']['clip'] = True
                else:
                    layer['mark'] = {'type': layer['mark'], 'clip': True}
    else:
        if 'mark' in new_state:
            if isinstance(new_state['mark'], dict):
                new_state['mark']['clip'] = True
            else:
                new_state['mark'] = {'type': new_state['mark'], 'clip': True}
    
    return {
        'success': True,
        'operation': 'zoom_x_region',
        'vega_state': new_state,
        'message': f'Zoomed to time range: {start} to {end}',
        'details': [f'View zoomed to show time range between {start} and {end}']
    }


def highlight_trend(state: Dict, trend_type: str = "increasing") -> Dict[str, Any]:
    """ - """
    new_state = copy.deepcopy(state)
    
    #  x  y 
    if 'layer' in new_state and len(new_state['layer']) > 0:
        encoding = new_state['layer'][0].get('encoding', {})
    else:
        encoding = new_state.get('encoding', {})
    
    y_field = encoding.get('y', {}).get('field')
    x_field = encoding.get('x', {}).get('field')
    
    if not y_field or not x_field:
        return {
            'success': False,
            'error': 'Cannot find x or y field for trend line'
        }
    
    #  layer， layer 
    if 'layer' not in new_state:
        original_layer = copy.deepcopy(new_state)
        #  mark  encoding， layer 
        for key in ['mark', 'encoding']:
            if key in original_layer:
                del original_layer[key]
        
        new_state = original_layer
        new_state['layer'] = [{
            'mark': state.get('mark', 'line'),
            'encoding': state.get('encoding', {})
        }]
    
    # 
    new_state['layer'].append({
        'mark': {
            'type': 'line',
            'color': 'red',
            'strokeDash': [5, 5],
            'strokeWidth': 2
        },
        'transform': [{
            'regression': y_field,
            'on': x_field
        }],
        'encoding': {
            'x': {'field': x_field, 'type': encoding['x'].get('type', 'temporal')},
            'y': {'field': y_field, 'type': encoding['y'].get('type', 'quantitative')}
        }
    })
    
    return {
        'success': True,
        'operation': 'highlight_trend',
        'vega_state': new_state,
        'message': f'Added {trend_type} regression trend line',
        'details': [f'Trend line shows overall {trend_type} pattern']
    }



def detect_anomalies(state: Dict, threshold: float = 2.0) -> Dict[str, Any]:
    """ - """
    import numpy as np
    
    data = _get_data_values(state)
    
    # （ layer ）
    if 'layer' in state and len(state['layer']) > 0:
        encoding = state['layer'][0].get('encoding', {})
    else:
        encoding = state.get('encoding', {})
    
    y_field = encoding.get('y', {}).get('field')
    x_field = encoding.get('x', {}).get('field')
    
    if not data or not y_field:
        return {'success': False, 'error': 'Missing data or y field'}
    
    values = [row.get(y_field) for row in data if row.get(y_field) is not None]
    
    if len(values) < 3:
        return {'success': False, 'error': 'Not enough data for anomaly detection'}
    
    # 
    mean = np.mean(values)
    std = np.std(values)
    
    # 
    anomaly_data = []
    for row in data:
        val = row.get(y_field)
        if val is not None and abs(val - mean) > threshold * std:
            anomaly_data.append(row)
    
    new_state = copy.deepcopy(state)
    
    # ，
    if anomaly_data:
        #  layer 
        if 'layer' not in new_state:
            original_layer = copy.deepcopy(new_state)
            for key in ['mark', 'encoding']:
                if key in original_layer:
                    del original_layer[key]
            
            new_state = original_layer
            new_state['layer'] = [{
                'mark': state.get('mark', 'line'),
                'encoding': state.get('encoding', {})
            }]
        
        # 
        new_state['layer'].append({
            'data': {'values': anomaly_data},
            'mark': {
                'type': 'point',
                'color': 'red',
                'size': 100,
                'filled': True
            },
            'encoding': {
                'x': {'field': x_field, 'type': encoding['x'].get('type', 'temporal')} if x_field else {},
                'y': {'field': y_field, 'type': encoding['y'].get('type', 'quantitative')},
                'tooltip': [
                    {'field': x_field, 'type': encoding['x'].get('type', 'temporal'), 'title': 'Time'} if x_field else {},
                    {'field': y_field, 'type': 'quantitative', 'title': 'Value (Anomaly)'}
                ]
            }
        })
    
    return {
        'success': True,
        'operation': 'detect_anomalies',
        'vega_state': new_state,
        'anomaly_count': len(anomaly_data),
        'anomalies': anomaly_data[:10],
        'message': f'Detected and highlighted {len(anomaly_data)} anomalies (threshold={threshold} std)',
        'details': [
            f'Mean: {mean:.2f}, Std: {std:.2f}',
            f'Anomalies are values beyond {threshold} standard deviations from mean',
            f'Anomalies marked with red points on the chart'
        ]
    }


def bold_lines(state: Dict, line_names: List[str], line_field: str = None) -> Dict[str, Any]:
    """
    
    
    Args:
        state: Vega-Lite
        line_names: 
        line_field: （， color/detail ）
    """
    import json
    new_state = copy.deepcopy(state)
    
    # （ color， detail）
    if line_field is None:
        if 'layer' in new_state and len(new_state['layer']) > 0:
            encoding = new_state['layer'][0].get('encoding', {})
        else:
            encoding = new_state.get('encoding', {})
        
        color_enc = encoding.get('color', {})
        line_field = color_enc.get('field')
        
        if not line_field:
            #  detail 
            detail_enc = encoding.get('detail', {})
            line_field = detail_enc.get('field')
    
    if not line_field:
        return {
            'success': False,
            'error': 'Cannot find line grouping field. Please specify line_field parameter.'
        }
    
    #  strokeWidth （）
    lines_json = json.dumps(line_names)
    stroke_width_encoding = {
        'condition': {
            'test': f'indexof({lines_json}, {_datum_ref(line_field)}) >= 0',
            'value': 4
        },
        'value': 1
    }
    
    #  spec
    if 'layer' in new_state:
        for layer in new_state['layer']:
            mark = layer.get('mark', {})
            if (isinstance(mark, dict) and mark.get('type') == 'line') or mark == 'line':
                if 'encoding' not in layer:
                    layer['encoding'] = {}
                layer['encoding']['strokeWidth'] = stroke_width_encoding
    else:
        if 'encoding' not in new_state:
            new_state['encoding'] = {}
        new_state['encoding']['strokeWidth'] = stroke_width_encoding
    
    return {
        'success': True,
        'operation': 'bold_lines',
        'vega_state': new_state,
        'message': f'Bolded lines: {line_names}'
    }


def filter_lines(state: Dict, lines_to_remove: List[str], line_field: str = None) -> Dict[str, Any]:
    """
    
    
    Args:
        state: Vega-Lite
        lines_to_remove: 
        line_field: （， color/detail ）
    """
    import json
    new_state = copy.deepcopy(state)
    
    # （ color， detail）
    if line_field is None:
        if 'layer' in new_state and len(new_state['layer']) > 0:
            encoding = new_state['layer'][0].get('encoding', {})
        else:
            encoding = new_state.get('encoding', {})
        
        color_enc = encoding.get('color', {})
        line_field = color_enc.get('field')
        
        if not line_field:
            detail_enc = encoding.get('detail', {})
            line_field = detail_enc.get('field')
    
    if not line_field:
        return {
            'success': False,
            'error': 'Cannot find line grouping field. Please specify line_field parameter.'
        }
    
    #  filter transform 
    if 'transform' not in new_state:
        new_state['transform'] = []
    
    lines_json = json.dumps(lines_to_remove)
    new_state['transform'].append({
        'filter': f'indexof({lines_json}, {_datum_ref(line_field)}) < 0'
    })
    
    return {
        'success': True,
        'operation': 'filter_lines',
        'vega_state': new_state,
        'message': f'Filtered out lines: {lines_to_remove}'
    }


def show_moving_average(state: Dict, window_size: int = 3) -> Dict[str, Any]:
    """
    
    
    Args:
        state: Vega-Lite
        window_size: 
    """
    new_state = copy.deepcopy(state)
    
    # 
    if 'layer' in new_state and len(new_state['layer']) > 0:
        encoding = new_state['layer'][0].get('encoding', {})
    else:
        encoding = new_state.get('encoding', {})
    
    y_field = encoding.get('y', {}).get('field')
    x_field = encoding.get('x', {}).get('field')
    
    if not y_field or not x_field:
        return {
            'success': False,
            'error': 'Cannot find x or y field for moving average'
        }
    
    #  layer， layer 
    if 'layer' not in new_state:
        original_layer = copy.deepcopy(new_state)
        for key in ['mark', 'encoding']:
            if key in original_layer:
                del original_layer[key]
        
        new_state = original_layer
        new_state['layer'] = [{
            'mark': state.get('mark', 'line'),
            'encoding': state.get('encoding', {})
        }]
    
    # （）
    color_field = encoding.get('color', {}).get('field')
    detail_field = encoding.get('detail', {}).get('field')
    group_field = color_field or detail_field
    
    # 
    ma_field = f'{y_field}_ma'
    
    #  window transform 
    window_transform = {
        'window': [{
            'op': 'mean',
            'field': y_field,
            'as': ma_field
        }],
        'frame': [-(window_size - 1), 0],
        'sort': [{'field': x_field, 'order': 'ascending'}]  #  x ，
    }
    
    # （），
    if group_field:
        window_transform['groupby'] = [group_field]
    
    # 
    ma_encoding = {
        'x': {'field': x_field, 'type': encoding['x'].get('type', 'temporal')},
        'y': {'field': ma_field, 'type': 'quantitative'}
    }
    
    # /， lines 
    if color_field and isinstance(encoding.get('color'), dict):
        ma_encoding['color'] = copy.deepcopy(encoding.get('color'))
    elif detail_field and isinstance(encoding.get('detail'), dict):
        ma_encoding['detail'] = copy.deepcopy(encoding.get('detail'))
    
    new_state['layer'].append({
        'mark': {
            'type': 'line',
            'color': 'orange',
            'strokeWidth': 3,
            'opacity': 0.8
        },
        'transform': [window_transform],
        'encoding': ma_encoding
    })
    
    return {
        'success': True,
        'operation': 'show_moving_average',
        'vega_state': new_state,
        'message': f'Added {window_size}-period moving average line'
    }


def focus_lines(
    state: Dict,
    lines: List[str],
    line_field: Optional[str] = None,
    mode: str = "dim",
    dim_opacity: float = 0.08,
) -> Dict[str, Any]:
    """
    ：，。
    
    Args:
        state: Vega-Lite
        lines: 
        line_field: （， color.field  detail.field）
        mode: 'dim'（）
        dim_opacity: mode='dim' 
    """
    import json

    new_state = copy.deepcopy(state)

    if not isinstance(lines, list) or not lines:
        return {'success': False, 'error': 'lines must be a non-empty list'}

    # （ color， detail）
    if line_field is None:
        if 'layer' in new_state and len(new_state['layer']) > 0:
            encoding = new_state['layer'][0].get('encoding', {})
        else:
            encoding = new_state.get('encoding', {})

        line_field = (encoding.get('color', {}) or {}).get('field')
        if not line_field:
            line_field = (encoding.get('detail', {}) or {}).get('field')

    if not line_field:
        return {'success': False, 'error': 'Cannot find line grouping field. Please specify line_field.'}

    lines_json = json.dumps(lines)

    ref = _datum_ref(line_field)
    if mode == "hide":
        if 'transform' not in new_state:
            new_state['transform'] = []
        new_state['transform'].append({
            'filter': f'indexof({lines_json}, {ref}) >= 0',
            '_avs_tag': 'focus_lines'
        })
    else:
        opacity_encoding = {
            'condition': {
                'test': f'indexof({lines_json}, {ref}) >= 0',
                'value': 1.0
            },
            'value': float(dim_opacity)
        }

        if 'layer' in new_state:
            for layer in new_state.get('layer', []):
                mark = layer.get('mark', {})
                if (isinstance(mark, dict) and mark.get('type') == 'line') or mark == 'line':
                    if 'encoding' not in layer:
                        layer['encoding'] = {}
                    layer['encoding']['opacity'] = opacity_encoding
        else:
            if 'encoding' not in new_state:
                new_state['encoding'] = {}
            new_state['encoding']['opacity'] = opacity_encoding

    return {
        'success': True,
        'operation': 'focus_lines',
        'vega_state': new_state,
        'message': f'Focused on lines: {lines} (mode={mode})'
    }


def drill_down_x_axis(
    state: Dict,
    level: str,
    value: int,
    parent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    ： →  → 
    
    ：，。
    ，。
    
    （），：
    - ：12
    - ：
    
    Args:
        state: Vega-Lite 
        level: 'year' | 'month' | 'date'
        value:  level 
               - year: 4 2023
               - month: 1-12 (1=，12=)
               - date: 1-31
        parent: ， {'year': 2023}  {'year': 2023, 'month': 3}
    
    Returns:
        
    """
    new_state = copy.deepcopy(state)
    
    # 
    state = new_state.get('_line_drilldown_state')
    if not isinstance(state, dict):
        state = {}
    
    #  transform  encoding，
    if 'original_transform' not in state:
        state['original_transform'] = copy.deepcopy(new_state.get('transform', []))
        state['original_encoding'] = copy.deepcopy(new_state.get('encoding', {}))
        state['original_title'] = new_state.get('title', '')
        
        # 
        #  transform  timeUnit 
        raw_time_field = None
        for t in state['original_transform']:
            if isinstance(t, dict) and 'timeUnit' in t and 'field' in t:
                raw_time_field = t['field']
                break
        
        # ， x encoding 
        if not raw_time_field:
            x_enc = state['original_encoding'].get('x', {})
            raw_time_field = x_enc.get('field', 'date')
            #  x （ year_date），
            if raw_time_field and '_' in raw_time_field:
                # year_date, month_date  ->  date
                possible_raw = raw_time_field.split('_')[-1]
                # 
                data = _get_data_values(new_state)
                if data and possible_raw in data[0]:
                    raw_time_field = possible_raw
        
        state['raw_time_field'] = raw_time_field or 'date'
        
        # 
        #  transform  aggregate 
        raw_value_field = None
        for t in state['original_transform']:
            if isinstance(t, dict) and 'aggregate' in t:
                aggs = t['aggregate']
                if isinstance(aggs, list) and len(aggs) > 0:
                    raw_value_field = aggs[0].get('field')
                    break
        
        # ， y encoding 
        if not raw_value_field:
            y_enc = state['original_encoding'].get('y', {})
            y_field = y_enc.get('field', '')
            # （ total_sales），
            if y_field.startswith('total_') or y_field.startswith('sum_'):
                possible_raw = y_field.replace('total_', '').replace('sum_', '')
                data = _get_data_values(new_state)
                if data and possible_raw in data[0]:
                    raw_value_field = possible_raw
            else:
                raw_value_field = y_field
        
        state['raw_value_field'] = raw_value_field or 'value'
        
        # （color encoding）
        color_enc = state['original_encoding'].get('color', {})
        state['group_field'] = color_enc.get('field')
    
    # 
    raw_date_field = state.get('raw_time_field', 'date')
    raw_value_field = state.get('raw_value_field', 'value')
    group_field = state.get('group_field')
    
    # （ parent > ）
    p = {}
    if isinstance(state.get('parent'), dict):
        p.update(state.get('parent'))
    if isinstance(parent, dict):
        p.update(parent)
    
    #  level
    level = str(level).lower().strip()
    
    try:
        value = int(value)
    except (TypeError, ValueError):
        return {'success': False, 'error': f'Invalid value: {value}; expected integer'}
    
    #  transform：，
    new_transforms = []
    title_suffix = ""
    
    #  groupby 
    groupby_fields = ['_time_field_']  # ，
    if group_field:
        groupby_fields.append(group_field)
    
    if level == 'year':
        # ，
        if value < 1900 or value > 2100:
            return {'success': False, 'error': f'Invalid year: {value}'}
        
        # 1. 
        new_transforms.append({
            'filter': f'year(datum.{raw_date_field}) == {value}',
            '_avs_tag': 'line_drilldown_axis'
        })
        # 2. 
        new_transforms.append({
            'timeUnit': 'yearmonth',
            'field': raw_date_field,
            'as': 'month_date',
            '_avs_tag': 'line_drilldown_axis'
        })
        
        #  groupby
        month_groupby = ['month_date']
        if group_field:
            month_groupby.append(group_field)
        
        new_transforms.append({
            'aggregate': [{'op': 'sum', 'field': raw_value_field, 'as': 'total_value'}],
            'groupby': month_groupby,
            '_avs_tag': 'line_drilldown_axis'
        })
        
        state['parent'] = {'year': value}
        title_suffix = f'{value} monthly trend'
        
        #  encoding
        new_state['encoding'] = {
            'x': {
                'field': 'month_date',
                'type': 'temporal',
                'title': 'Month',
                'axis': {'format': '%Y-%m'}
            },
            'y': {
                'field': 'total_value',
                'type': 'quantitative',
                'title': f'Monthly total {raw_value_field}'
            },
            'color': state['original_encoding'].get('color', {})
        }
        
    elif level == 'month':
        # ，
        year_val = p.get('year')
        if not year_val:
            return {'success': False, 'error': 'Month drill-down requires parent.year'}
        
        if value < 1 or value > 12:
            return {'success': False, 'error': f'Invalid month: {value}; expected 1-12'}
        
        # Vega  month()  0-11
        vega_month = value - 1
        
        # 1. 
        new_transforms.append({
            'filter': f'year(datum.{raw_date_field}) == {year_val} && month(datum.{raw_date_field}) == {vega_month}',
            '_avs_tag': 'line_drilldown_axis'
        })
        # 2. （）
        new_transforms.append({
            'timeUnit': 'yearmonthdate',
            'field': raw_date_field,
            'as': 'day_date',
            '_avs_tag': 'line_drilldown_axis'
        })
        
        #  groupby
        day_groupby = ['day_date']
        if group_field:
            day_groupby.append(group_field)
        
        new_transforms.append({
            'aggregate': [{'op': 'sum', 'field': raw_value_field, 'as': 'total_value'}],
            'groupby': day_groupby,
            '_avs_tag': 'line_drilldown_axis'
        })
        
        state['parent'] = {'year': year_val, 'month': value}
        title_suffix = f'{year_val}-{value} daily trend'
        
        #  encoding
        new_state['encoding'] = {
            'x': {
                'field': 'day_date',
                'type': 'temporal',
                'title': 'Date',
                'axis': {'format': '%m-%d'}
            },
            'y': {
                'field': 'total_value',
                'type': 'quantitative',
                'title': f'Daily {raw_value_field}'
            },
            'color': state['original_encoding'].get('color', {})
        }
        
    elif level == 'date':
        # 
        return {'success': False, 'error': 'Daily data is the finest granularity; cannot drill further'}
        
    else:
        return {'success': False, 'error': f'Invalid level: {level}; expected year/month/date'}
    
    #  transform（ transform）
    new_state['transform'] = new_transforms
    
    # 
    new_state['title'] = title_suffix
    
    #  tooltip
    if 'tooltip' in state['original_encoding']:
        #  tooltip
        tooltip_list = [
            {'field': new_state['encoding']['x']['field'], 'type': 'temporal', 'title': 'Time'},
        ]
        if group_field:
            tooltip_list.append({'field': group_field, 'type': 'nominal', 'title': group_field})
        tooltip_list.append({'field': 'total_value', 'type': 'quantitative', 'title': raw_value_field, 'format': ',.0f'})
        new_state['encoding']['tooltip'] = tooltip_list
    
    # 
    new_state['_line_drilldown_state'] = state
    
    return {
        'success': True,
        'operation': 'drill_down_x_axis',
        'vega_state': new_state,
        'message': f'Drilled down to {title_suffix}',
        'current_level': level,
        'parent': state.get('parent', {})
    }


def reset_drilldown_x_axis(state: Dict) -> Dict[str, Any]:
    """
    ，。
    
    Args:
        state: Vega-Lite 
    
    Returns:
        
    """
    new_state = copy.deepcopy(state)
    
    # 
    state = new_state.get('_line_drilldown_state')
    if not isinstance(state, dict):
        return {
            'success': True,
            'operation': 'reset_drilldown_x_axis',
            'vega_state': new_state,
            'message': 'No drill-down state to reset'
        }
    
    #  transform
    original_transform = state.get('original_transform')
    if original_transform is not None:
        new_state['transform'] = copy.deepcopy(original_transform)
    else:
        #  transform， transform
        if 'transform' in new_state:
            new_state['transform'] = [
                t for t in new_state['transform']
                if not (isinstance(t, dict) and t.get('_avs_tag') == 'line_drilldown_axis')
            ]
    
    #  encoding
    original_encoding = state.get('original_encoding')
    if original_encoding:
        new_state['encoding'] = copy.deepcopy(original_encoding)
    
    # 
    original_title = state.get('original_title')
    if original_title:
        new_state['title'] = original_title
    
    # 
    if '_line_drilldown_state' in new_state:
        del new_state['_line_drilldown_state']
    
    return {
        'success': True,
        'operation': 'reset_drilldown_x_axis',
        'vega_state': new_state,
        'message': 'Reset to initial yearly view'
    }


def resample_x_axis(
    state: Dict,
    granularity: str,
    agg: str = "mean",
) -> Dict[str, Any]:
    """
    （）：。
    
    ：
    - /
    - ，/
    
    Args:
        state: Vega-Lite 
        granularity:  ("day" | "week" | "month" | "quarter" | "year")
        agg:  ("mean" | "sum" | "max" | "min" | "median")， mean
    
    Returns:
        
    """
    new_state = copy.deepcopy(state)
    
    #  Vega-Lite timeUnit
    GRANULARITY_MAP = {
        "day": "yearmonthdate",
        "week": "yearweek",
        "month": "yearmonth",
        "quarter": "yearquarter",
        "year": "year",
    }
    
    granularity_lower = str(granularity).lower().strip()
    if granularity_lower not in GRANULARITY_MAP:
        return {
            'success': False,
            'error': f'Unsupported granularity: {granularity}. Use one of {list(GRANULARITY_MAP.keys())}'
        }
    
    target_timeunit = GRANULARITY_MAP[granularity_lower]
    
    # 
    ALLOWED_AGG = {"mean", "sum", "max", "min", "median", "count"}
    agg_lower = str(agg).lower().strip()
    if agg_lower not in ALLOWED_AGG:
        return {
            'success': False,
            'error': f'Unsupported agg: {agg}. Use one of {sorted(list(ALLOWED_AGG))}'
        }
    
    # 
    time_field = _get_time_field(new_state)
    if not time_field:
        return {'success': False, 'error': 'Cannot find temporal field in encoding'}
    
    # 
    state = new_state.get('_resample_state')
    if not isinstance(state, dict):
        state = {}
    if 'original_encoding' not in state:
        if 'layer' in new_state and len(new_state['layer']) > 0:
            state['original_encoding'] = copy.deepcopy(new_state['layer'][0].get('encoding', {}))
        else:
            state['original_encoding'] = copy.deepcopy(new_state.get('encoding', {}))
    
    # 
    if 'layer' in new_state and len(new_state['layer']) > 0:
        encoding = new_state['layer'][0].get('encoding', {})
    else:
        encoding = new_state.get('encoding', {})
    
    x_enc = encoding.get('x', {})
    y_enc = encoding.get('y', {})
    
    # 
    if x_enc.get('field') == time_field or x_enc.get('type') == 'temporal':
        time_axis = 'x'
        value_axis = 'y'
    else:
        time_axis = 'y'
        value_axis = 'x'
    
    #  timeUnit
    def _update_encoding(enc: Dict) -> None:
        if time_axis in enc:
            enc[time_axis]['timeUnit'] = target_timeunit
            enc[time_axis]['type'] = 'temporal'
        
        # 
        if value_axis in enc:
            value_field = enc[value_axis].get('field')
            if value_field:
                enc[value_axis]['aggregate'] = agg_lower
    
    if 'layer' in new_state:
        for layer in new_state['layer']:
            if 'encoding' in layer:
                _update_encoding(layer['encoding'])
    else:
        if 'encoding' not in new_state:
            new_state['encoding'] = {}
        _update_encoding(new_state['encoding'])
    
    # 
    state['current_granularity'] = granularity_lower
    state['current_agg'] = agg_lower
    new_state['_resample_state'] = state
    
    return {
        'success': True,
        'operation': 'resample_x_axis',
        'vega_state': new_state,
        'message': f'Resampled time to {granularity} with {agg} aggregation'
    }


def reset_resample_x_axis(state: Dict) -> Dict[str, Any]:
    """
    ，。
    """
    new_state = copy.deepcopy(state)
    
    state = new_state.get('_resample_state')
    if not isinstance(state, dict):
        return {
            'success': True,
            'operation': 'reset_resample_x_axis',
            'vega_state': new_state,
            'message': 'No resample state to reset'
        }
    
    original_encoding = state.get('original_encoding')
    if original_encoding:
        if 'layer' in new_state and len(new_state['layer']) > 0:
            new_state['layer'][0]['encoding'] = copy.deepcopy(original_encoding)
        else:
            new_state['encoding'] = copy.deepcopy(original_encoding)
    
    if '_resample_state' in new_state:
        del new_state['_resample_state']
    
    return {
        'success': True,
        'operation': 'reset_resample_x_axis',
        'vega_state': new_state,
        'message': 'Reset to original time granularity'
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


__all__ = [
    'zoom_x_region',
    'highlight_trend',
    'detect_anomalies',
    'bold_lines',
    'filter_lines',
    'show_moving_average',
    'focus_lines',
    'drill_down_x_axis',
    'reset_drilldown_x_axis',
    'resample_x_axis',
    'reset_resample_x_axis',
    'change_encoding',
]

for _fn_name in __all__:
    _fn = globals().get(_fn_name)
    if callable(_fn):
        globals()[_fn_name] = tool_output(_fn)
