"""Common perception and action tools (state-based; no view_id)."""

import json
import copy
import hashlib
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
from datetime import datetime
from state_manager import DataStore, tool_output


def _datum_ref(field: str) -> str:
    """Vega expr: datum access that supports field names with spaces/special chars."""
    if not field:
        return "datum"
    s = str(field).replace("\\", "\\\\").replace("'", "\\'")
    return f"datum['{s}']"


# ==================== Perception APIs ====================

def _get_primary_encoding(state: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer layer[0].encoding when present (common for line/scatter)."""
    if isinstance(state.get('layer'), list) and len(state['layer']) > 0:
        enc = state['layer'][0].get('encoding', {})
        return enc if isinstance(enc, dict) else {}
    enc = state.get('encoding', {})
    return enc if isinstance(enc, dict) else {}


def _coerce_comparable(v: Any) -> Any:
    """Coerce values for range comparisons (numbers, ISO dates)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        # number-like
        try:
            return float(s)
        except Exception:
            pass
        # ISO-ish datetime
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return s
    return v


def _apply_selected_region(data: List[Dict[str, Any]], state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply _selected_region (from scatter tools) if present."""
    region = state.get('_selected_region')
    if not isinstance(region, dict):
        return data
    x_field = region.get('x_field')
    y_field = region.get('y_field')
    x_range = region.get('x_range')
    y_range = region.get('y_range')
    if not x_field or not y_field or not isinstance(x_range, list) or not isinstance(y_range, list):
        return data
    if len(x_range) != 2 or len(y_range) != 2:
        return data

    xl, xu = _coerce_comparable(x_range[0]), _coerce_comparable(x_range[1])
    yl, yu = _coerce_comparable(y_range[0]), _coerce_comparable(y_range[1])

    out: List[Dict[str, Any]] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        xv = _coerce_comparable(r.get(x_field))
        yv = _coerce_comparable(r.get(y_field))
        if xv is None or yv is None:
            continue
        try:
            if xl <= xv <= xu and yl <= yv <= yu:
                out.append(r)
        except Exception:
            # if comparison fails, do not filter it out aggressively
            out.append(r)
    return out


def get_view_spec(state: Dict) -> Dict[str, Any]:
    """Return structured summary: mark, encoding, domains, transforms."""
    #  spec hash
    spec_str = json.dumps(state, sort_keys=True, default=str)
    spec_hash = hashlib.sha256(spec_str.encode()).hexdigest()[:16]
    
    # 
    chart_type = _detect_chart_type(state)
    
    # 
    data = _get_spec_data(state)
    data_count = len(data) if data else 0
    
    #  encoding（ layer）
    encoding = _get_primary_encoding(state)
    
    #  mark
    mark = state.get('mark', {})
    if isinstance(mark, str):
        mark = {'type': mark}
    
    # （ scale  encoding ， layer）
    visible_domain = _extract_visible_domain(state, data)
    
    #  transforms
    transforms = state.get('transform', [])
    #  transform
    transforms = [t for t in transforms if not t.get('_avs_tag')]
    
    #  selections（）
    selections = state.get('_avs_selections', [])
    
    return {
        'success': True,
        'spec_hash': f'sha256:{spec_hash}',
        'payload': {
            'chart_type': chart_type,
            'title': state.get('title', ''),
            'data_count': data_count,
            'mark': mark,
            'encoding': _simplify_encoding(encoding),
            'visible_domain': visible_domain,
            'transforms': transforms,
            'selections': selections
        }
    }


def get_data(state: Dict, scope: str = 'all') -> Dict[str, Any]:
    """
    Return tabular rows for scope: all | filter | visible | selected.
    """
    data = _get_spec_data(state)
    
    if not data:
        return {
            'success': False,
            'error': 'No data available in spec'
        }
    
    total_count = len(data)
    fields = list(data[0].keys()) if data else []
    
    transforms = state.get('transform', [])

    if scope == 'all':
        result_data = data

    elif scope == 'filter':
        result_data = _apply_filters(data, transforms)

    elif scope == 'visible':
        # visible = filter transforms + scale.domain + selection region (if any)
        result_data = _apply_filters(data, transforms)
        result_data = _filter_by_domain(result_data, state)
        result_data = _apply_selected_region(result_data, state)
        selections = state.get('_avs_selections', [])
        if selections:
            result_data = _apply_selections(result_data, selections)

    elif scope == 'selected':
        # Prefer _selected_region; fallback to _avs_selections.
        result_data = _apply_filters(data, transforms)
        result_data = _apply_selected_region(result_data, state)
        if result_data == data:
            selections = state.get('_avs_selections', [])
            result_data = _apply_selections(result_data, selections) if selections else []
    else:
        return {
            'success': False,
            'error': f'Unknown scope: {scope}. Valid values: all, filter, visible, selected'
        }
    
    field_preview = fields[:6]
    field_suffix = f", +{len(fields) - len(field_preview)} more" if len(fields) > len(field_preview) else ""
    message = (
        f"scope={scope}, returned={len(result_data)}/{total_count}, "
        f"fields={len(fields)} [{', '.join(map(str, field_preview))}{field_suffix}]"
    )

    return {
        'success': True,
        'scope': scope,
        'total_count': total_count,
        'returned_count': len(result_data),
        'fields': fields,
        'data': result_data,
        'message': message
    }


def get_data_summary(state: Dict, scope: str = 'all') -> Dict[str, Any]:
    """Numeric and categorical summaries for rows in scope."""
    #  get_data  scope 
    data_result = get_data(state, scope=scope if scope else 'all')
    if not data_result.get('success'):
        return {'success': False, 'error': data_result.get('error', 'No data available')}
    data = data_result.get('data', [])
    
    if not data:
        return {'success': False, 'error': 'No data available'}
    
    # 
    summary = {
        'count': len(data),
        'numeric_fields': {},
        'categorical_fields': {}
    }
    
    if data:
        sample = data[0]
        for field_name in sample.keys():
            values = [row.get(field_name) for row in data if row.get(field_name) is not None]
            
            if not values:
                continue
            
            if isinstance(values[0], (int, float)):
                summary['numeric_fields'][field_name] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)),
                    'min': float(np.min(values)),
                    'max': float(np.max(values)),
                    'median': float(np.median(values))
                }
            else:
                unique_values = list(set(values))
                value_counts = {v: values.count(v) for v in unique_values}
                
                summary['categorical_fields'][field_name] = {
                    'unique_count': len(unique_values),
                    'categories': unique_values[:20],
                    'distribution': value_counts
                }
    
    message = (
        f"summary={summary} for scope={scope}"

    )

    return {
        'success': True,
        'scope': scope,
        'summary': summary,
        'message': message
    }


def get_tooltip_data(state: Dict, position: Tuple[float, float]) -> Dict[str, Any]:
    """Approximate nearest data row to the given x/y position."""
    data = _get_spec_data(state)
    
    x_pos, y_pos = position
    x_field = _get_encoding_field(state, 'x')
    y_field = _get_encoding_field(state, 'y')
    
    if not x_field or not y_field:
        return {'success': False, 'message': 'Cannot find x/y fields'}
    
    closest_point = None
    min_distance = float('inf')
    
    for row in data:
        x_val = row.get(x_field)
        y_val = row.get(y_field)
        
        if x_val is not None and y_val is not None:
            distance = np.sqrt((x_val - x_pos)**2 + (y_val - y_pos)**2)
            if distance < min_distance:
                min_distance = distance
                closest_point = row
    
    if closest_point:
        return {'success': True, 'data': closest_point, 'distance': min_distance}
    
    return {'success': False, 'message': 'No data point found'}

def change_encoding(state: Dict, channel: str, field: str, type: Optional[str] = None) -> Dict[str, Any]:
    """
    Modify the field mapping of the specified encoding channel

    Args:
        state: Vega spec
        channel: encoding channel ("x", "y", "color", "size", "shape")
        field: new field name
        type: optional Vega-Lite type ("quantitative", "nominal", "ordinal", "temporal"); inferred from data if omitted
    """
    new_state = copy.deepcopy(state)
    
    # （）
    data = _get_spec_data(new_state)
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
    #  type，
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

# ====================  API (Action APIs) ====================

def reset_view(
    state: Dict,
    original_spec: Optional[Dict] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Reset view to original state.
    
    Reads original_spec from state._original_spec metadata field.
    If original_spec parameter is provided (for backward compatibility), it takes precedence.
    
    Args:
        state: Current view's state (contains metadata)
        original_spec: Original view's state (optional, for backward compatibility)
        
    Returns:
        Reset state
    """
    # Try parameter first (backward compatibility), then metadata, then context.
    if original_spec is None:
        original_spec = state.get('_original_spec')
    if original_spec is None and isinstance(context, dict):
        original_spec = context.get('original_spec')
    
    if original_spec is None:
        return {
            'success': False,
            'error': 'original_spec not found in state metadata or context'
        }

    return {
        'success': True,
        'operation': 'reset_view',
        'vega_state': copy.deepcopy(original_spec),
        'message': 'View reset to original state'
    }


def undo_view(
    state: Dict,
    spec_history: Optional[List[Dict]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Undo previous view, return previous version of state.
    
    Reads spec_history from state._spec_history metadata field.
    If spec_history parameter is provided (for backward compatibility), it takes precedence.
    
    Args:
        state: Current view's state (contains metadata)
        spec_history: View history list (optional, for backward compatibility; will be modified using pop)
    """
    # Try parameter first (backward compatibility), then metadata, then context.
    if spec_history is None:
        spec_history = state.get('_spec_history')
    if spec_history is None and isinstance(context, dict):
        spec_history = context.get('spec_history')
    
    if spec_history is None:
        return {'success': False, 'error': 'spec_history not found in state metadata or context'}

    if not isinstance(spec_history, list):
        return {'success': False, 'error': 'spec_history must be a list'}

    if not spec_history:
        return {'success': False, 'error': 'no previous view to undo'}

    prev_spec = spec_history.pop()  # LIFO
    return {
        'success': True,
        'operation': 'undo_view',
        'vega_state': copy.deepcopy(prev_spec),
        'message': 'Restored previous view'
    }


def render_chart(state: Dict) -> Dict[str, Any]:
    """Render the current spec to PNG via VegaService."""
    from core.vega_service import get_vega_service
    from core.utils import app_logger
    
    try:
        vega_service = get_vega_service()
        render_result = vega_service.render(state)
        
        if render_result.get("success"):
            return {
                'success': True,
                'operation': 'render',
                'image_base64': render_result["image_base64"],
                'renderer': render_result.get("renderer"),
                'message': f'Rendered using {render_result.get("renderer")}'
            }
        else:
            return {
                'success': False,
                'operation': 'render',
                'error': render_result.get("error")
            }
    except Exception as e:
        return {'success': False, 'operation': 'render', 'error': str(e)}


# ==================== Helpers ====================

def _get_encoding_field(state: Dict, channel: str) -> Optional[str]:
    """Return encoding field name for channel."""
    return state.get('encoding', {}).get(channel, {}).get('field')


def _get_primary_category_field(state: Dict) -> str:
    """Guess nominal field from color/x/y."""
    encoding = state.get('encoding', {})
    for channel in ['color', 'x', 'y']:
        if channel in encoding:
            field = encoding[channel].get('field')
            field_type = encoding[channel].get('type')
            if field and field_type in ['nominal', 'ordinal']:
                return field
    return 'category'


def _infer_field_type(state: Dict, field_name: str) -> str:
    """Infer quantitative/nominal/temporal from sample values."""
    data = _get_spec_data(state)
    if not data:
        return 'nominal'
    
    for row in data:
        value = row.get(field_name)
        if value is not None:
            if isinstance(value, (int, float)):
                return 'quantitative'
            elif isinstance(value, str):
                if any(sep in value for sep in ['-', '/', ':']):
                    return 'temporal'
                return 'nominal'
    return 'nominal'


def _get_spec_data(state: Dict) -> List[Dict]:
    """Read data rows from Vega-Lite or Vega spec."""
    # Vega-Lite : data.values
    data_obj = state.get('data', {})
    if isinstance(data_obj, dict) and 'values' in data_obj:
        return data_obj['values']
    
    # Vega : data 
    if isinstance(data_obj, list):
        # 
        for d in data_obj:
            if isinstance(d, dict) and 'values' in d:
                return d['values']
    
    # Fallback to state-context data provider
    store_data = DataStore.get()
    if isinstance(store_data, dict) and isinstance(store_data.get("values"), list):
        return store_data["values"]
    if isinstance(store_data, list):
        for d in store_data:
            if isinstance(d, dict) and isinstance(d.get("values"), list):
                return d["values"]

    return []


def _detect_chart_type(state: Dict) -> str:
    """Heuristic chart kind from mark/schema."""
    #  Vega（ Vega-Lite）
    schema = state.get('$schema', '')
    if 'vega.github.io/schema/vega/' in schema and 'vega-lite' not in schema:
        #  marks 
        marks = state.get('marks', [])
        for mark in marks:
            mark_type = mark.get('type', '')
            if mark_type == 'rect' and 'group' in str(marks):
                return 'sankey_diagram'
        return 'vega_custom'
    
    # Vega-Lite:  mark 
    mark = state.get('mark', {})
    if isinstance(mark, str):
        mark_type = mark
    else:
        mark_type = mark.get('type', '')
    
    encoding = state.get('encoding', {})
    
    if mark_type == 'bar':
        return 'bar_chart'
    elif mark_type in ['line', 'trail']:
        return 'line_chart'
    elif mark_type in ['point', 'circle']:
        return 'scatter_plot'
    elif mark_type == 'rect':
        # 
        if 'color' in encoding:
            return 'heatmap'
        return 'rect_chart'
    elif mark_type == 'rule':
        return 'parallel_coordinates'
    
    return 'unknown'


def _simplify_encoding(encoding: Dict) -> Dict:
    """ encoding ，"""
    simplified = {}
    for channel, config in encoding.items():
        if isinstance(config, dict):
            simplified[channel] = {
                'field': config.get('field'),
                'type': config.get('type')
            }
            # 
            if 'aggregate' in config:
                simplified[channel]['aggregate'] = config['aggregate']
            if 'timeUnit' in config:
                simplified[channel]['timeUnit'] = config['timeUnit']
        else:
            simplified[channel] = config
    return simplified


def _extract_visible_domain(state: Dict, data: List[Dict]) -> Dict:
    """Best-effort x/y domains from scale or data min/max."""
    domain = {}
    encoding = _get_primary_encoding(state)
    
    for channel in ['x', 'y']:
        if channel in encoding:
            field = encoding[channel].get('field')
            field_type = encoding[channel].get('type')
            
            #  scale  domain
            scale = encoding[channel].get('scale', {})
            if 'domain' in scale:
                domain[channel] = scale['domain']
            elif field and data and field_type == 'quantitative':
                # 
                values = [row.get(field) for row in data if row.get(field) is not None]
                if values and all(isinstance(v, (int, float)) for v in values):
                    domain[channel] = [min(values), max(values)]
    
    return domain


def _apply_filters(data: List[Dict], transforms: List[Dict]) -> List[Dict]:
    """ transform  filter"""
    result = data
    
    for t in transforms:
        if 'filter' in t:
            filter_expr = t['filter']
            if isinstance(filter_expr, str):
                #  filter 
                result = _eval_filter_expr(result, filter_expr)
            elif isinstance(filter_expr, dict):
                # Vega-Lite filter object
                field = filter_expr.get('field')
                if 'equal' in filter_expr:
                    result = [r for r in result if r.get(field) == filter_expr['equal']]
                elif 'oneOf' in filter_expr:
                    result = [r for r in result if r.get(field) in filter_expr['oneOf']]
                elif 'range' in filter_expr:
                    rng = filter_expr['range']
                    result = [r for r in result if rng[0] <= r.get(field, 0) <= rng[1]]
    
    return result


def _eval_filter_expr(data: List[Dict], expr: str) -> List[Dict]:
    """ filter ， datum['field']  indexof"""
    # Vega  && / ||；Python eval  and / or
    py_expr = expr.replace("&&", " and ").replace("||", " or ")

    result = []

    class _Datum:
        """datum ， datum['field']  datum.field"""
        def __init__(self, row):
            self._row = row
        def __getitem__(self, key):
            return self._row.get(key)
        def __getattr__(self, key):
            return self._row.get(key)

    def _indexof(arr, val):
        """Vega indexof:  val  arr ， -1"""
        try:
            return arr.index(val)
        except (ValueError, AttributeError):
            return -1

    _safe_builtins = {'True': True, 'False': False, 'None': None}
    _namespace = {'datum': None, 'indexof': _indexof, '__builtins__': _safe_builtins}

    for row in data:
        try:
            _namespace['datum'] = _Datum(row)
            if eval(py_expr, _namespace):
                result.append(row)
        except Exception:
            result.append(row)

    return result


def _filter_by_domain(data: List[Dict], state: Dict) -> List[Dict]:
    """Filter rows to encoded scale domains when set."""
    encoding = _get_primary_encoding(state)
    result = data
    
    for channel in ['x', 'y']:
        if channel in encoding:
            field = encoding[channel].get('field')
            scale = encoding[channel].get('scale', {})
            domain = scale.get('domain')
            
            if field and domain and isinstance(domain, list) and len(domain) == 2:
                lb = _coerce_comparable(domain[0])
                ub = _coerce_comparable(domain[1])
                filtered = []
                for r in result:
                    if not isinstance(r, dict):
                        continue
                    rv = _coerce_comparable(r.get(field))
                    if rv is None:
                        continue
                    try:
                        if lb <= rv <= ub:
                            filtered.append(r)
                    except Exception:
                        # If comparison fails, keep row to avoid over-filtering.
                        filtered.append(r)
                result = filtered
    
    return result


def _apply_selections(data: List[Dict], selections: List[Dict]) -> List[Dict]:
    """Apply simple selection predicates to rows."""
    if not selections:
        return []
    
    result = data
    
    for sel in selections:
        field = sel.get('field')
        op = sel.get('op', '==')
        values = sel.get('values', [])
        
        if not field:
            continue
        
        if op == '==' or op == 'eq':
            if isinstance(values, list):
                result = [r for r in result if r.get(field) in values]
            else:
                result = [r for r in result if r.get(field) == values]
        elif op == '!=' or op == 'neq':
            if isinstance(values, list):
                result = [r for r in result if r.get(field) not in values]
            else:
                result = [r for r in result if r.get(field) != values]
        elif op == '>' or op == 'gt':
            val = values[0] if isinstance(values, list) else values
            result = [r for r in result if r.get(field, 0) > val]
        elif op == '>=' or op == 'gte':
            val = values[0] if isinstance(values, list) else values
            result = [r for r in result if r.get(field, 0) >= val]
        elif op == '<' or op == 'lt':
            val = values[0] if isinstance(values, list) else values
            result = [r for r in result if r.get(field, 0) < val]
        elif op == '<=' or op == 'lte':
            val = values[0] if isinstance(values, list) else values
            result = [r for r in result if r.get(field, 0) <= val]
        elif op == 'in':
            result = [r for r in result if r.get(field) in values]
        elif op == 'not_in':
            result = [r for r in result if r.get(field) not in values]
    
    return result


__all__ = [
    'get_view_spec',
    'get_data',
    'get_data_summary',
    'get_tooltip_data',
    'reset_view',
    'undo_view',
    'render_chart',
]

for _fn_name in __all__:
    _fn = globals().get(_fn_name)
    if callable(_fn):
        globals()[_fn_name] = tool_output(_fn)
