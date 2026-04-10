"""
（ -  state）
"""

from typing import Dict, Any, List, Union
import copy
import json
from state_manager import tool_output



def reorder_dimensions(state: Dict, dimension_order: List[str]) -> Dict[str, Any]:
    """（ fold ）"""
    new_state = copy.deepcopy(state)
    
    # 1:  fold transform
    fold_transform = None
    fold_index = -1
    transforms = new_state.get('transform', [])
    for i, transform in enumerate(transforms):
        if isinstance(transform, dict) and 'fold' in transform:
            fold_transform = transform
            fold_index = i
            break
    
    if fold_transform is not None:
        #  fold 
        current_fold = fold_transform['fold']
        if not isinstance(current_fold, list):
            return {'success': False, 'error': 'Fold transform does not contain a list'}
        
        missing_dims = [dim for dim in dimension_order if dim not in current_fold]
        if missing_dims:
            return {'success': False, 'error': f'Dimensions not found in fold: {missing_dims}'}
        
        extra_dims = [dim for dim in current_fold if dim not in dimension_order]
        if extra_dims:
            return {'success': False, 'error': f'Missing dimensions in dimension_order: {extra_dims}'}
        
        new_state['transform'][fold_index]['fold'] = dimension_order
        
        #  x  scale.domain
        def update_x_encoding_scale(obj):
            if isinstance(obj, dict):
                if 'encoding' in obj and isinstance(obj['encoding'], dict):
                    x_encoding = obj['encoding'].get('x')
                    if isinstance(x_encoding, dict) and x_encoding.get('field') == 'key':
                        if 'scale' not in x_encoding:
                            x_encoding['scale'] = {}
                        x_encoding['scale']['domain'] = dimension_order
                for value in obj.values():
                    update_x_encoding_scale(value)
            elif isinstance(obj, list):
                for item in obj:
                    update_x_encoding_scale(item)
        
        update_x_encoding_scale(new_state)
    else:
        # 2: （ fold， x.sort  x.scale.domain）
        def update_x_sort(obj):
            """ dimension  x  sort"""
            if isinstance(obj, dict):
                if 'encoding' in obj and isinstance(obj['encoding'], dict):
                    x_encoding = obj['encoding'].get('x')
                    if isinstance(x_encoding, dict) and x_encoding.get('field') in ['dimension', 'key', 'variable']:
                        x_encoding['sort'] = dimension_order
                        if 'scale' in x_encoding:
                            x_encoding['scale']['domain'] = dimension_order
                for value in obj.values():
                    update_x_sort(value)
            elif isinstance(obj, list):
                for item in obj:
                    update_x_sort(item)
        
        update_x_sort(new_state)
    
    return {
        'success': True,
        'operation': 'reorder_dimensions',
        'vega_state': new_state,
        'message': f'Reordered dimensions to {dimension_order}'
    }

def filter_dimension(state: Dict, dimension: str, range: List[float]) -> Dict[str, Any]:
    """Filter by dimension"""
    new_state = copy.deepcopy(state)
    
    min_val, max_val = range
    
    if 'transform' not in new_state:
        new_state['transform'] = []
    
    # find fold operation position
    fold_index = -1
    for i, transform in enumerate(new_state['transform']):
        if isinstance(transform, dict) and 'fold' in transform:
            fold_index = i
            break
    
    # build filter expression (adapted for wide format, using square brackets to access field names)
    filter_expr = f"datum['{dimension}'] >= {min_val} && datum['{dimension}'] <= {max_val}"
    
    if fold_index >= 0:
        # insert filter before fold (using wide format)
        new_state['transform'].insert(fold_index, {
            'filter': filter_expr
        })
    else:
        # if no fold, insert at beginning of transform array
        new_state['transform'].insert(0, {
            'filter': filter_expr
    })
    
    return {
        'success': True,
        'operation': 'filter_dimension',
        'vega_state': new_state,
        'message': f'Filtered {dimension} to [{min_val}, {max_val}]'
    }



def filter_by_category(state: Dict, field: str, values: Union[str, List[str]]) -> Dict[str, Any]:
    """
    （ fold ，）
    
    Args:
        state: Vega-Lite
        field: （ "Species", "product", "region"）
        values: 
    """
    new_state = copy.deepcopy(state)
    
    if not isinstance(values, list):
        values = [values]
    
    if 'transform' not in new_state:
        new_state['transform'] = []
    
    #  fold 
    fold_index = -1
    for i, transform in enumerate(new_state['transform']):
        if isinstance(transform, dict) and 'fold' in transform:
            fold_index = i
            break
    
    #  filter （）
    values_str = ','.join([f'"{v}"' for v in values])
    filter_expr = f"indexof([{values_str}], datum['{field}']) < 0"
    
    if fold_index >= 0:
        #  fold  filter（）
        new_state['transform'].insert(fold_index, {
            'filter': filter_expr
        })
    else:
        #  fold， transform 
        new_state['transform'].insert(0, {
            'filter': filter_expr
        })
    
    return {
        'success': True,
        'operation': 'filter_by_category',
        'vega_state': new_state,
        'message': f'Filtered {field} to: {values}'
    }



def highlight_category(state: Dict, field: str, values: Union[str, List[str]]) -> Dict[str, Any]:
    """
    ，
    
    Args:
        state: Vega-Lite
        field: （ "Species", "product", "region"）
        values: 
    """
    new_state = copy.deepcopy(state)
    
    if not isinstance(values, list):
        values = [values]
    
    #  layer 
    if 'layer' in new_state and isinstance(new_state['layer'], list):
        #  mark: "line"  layer
        line_layer_index = -1
        for i, layer in enumerate(new_state['layer']):
            if isinstance(layer, dict):
                mark = layer.get('mark')
                if (isinstance(mark, dict) and mark.get('type') == 'line') or mark == 'line':
                    line_layer_index = i
                    break
        
        if line_layer_index >= 0:
            #  layer  encoding  opacity
            layer = new_state['layer'][line_layer_index]
            if 'encoding' not in layer:
                layer['encoding'] = {}
            
            #  opacity （）
            values_json = json.dumps(values)
            layer['encoding']['opacity'] = {
                'condition': {
                    'test': f"indexof({values_json}, datum['{field}']) >= 0",
                    'value': 1.0
                },
                'value': 0.1
            }
        else:
            return {
                'success': False,
                'error': 'No line layer found in state'
            }
    else:
        #  layer， encoding （）
        if 'encoding' not in new_state:
            new_state['encoding'] = {}
        
        values_json = json.dumps(values)
        new_state['encoding']['opacity'] = {
            'condition': {
                'test': f"indexof({values_json}, datum['{field}']) >= 0",
                'value': 1.0
            },
            'value': 0.1
        }
    
    return {
        'success': True,
        'operation': 'highlight_category',
        'vega_state': new_state,
        'message': f'Highlighted {field}: {values}'
    }


def hide_dimensions(
    state: Dict,
    dimensions: List[str],
    mode: str = "hide",
) -> Dict[str, Any]:
    """
    /。
    
    ：
    - ，
    - （show ）
    
    Args:
        state: Vega-Lite 
        dimensions: 
        mode: "hide"（） "show"（）， hide
    
    Returns:
        
    """
    new_state = copy.deepcopy(state)
    
    mode_lower = str(mode).lower().strip()
    if mode_lower not in ("hide", "show"):
        return {
            'success': False,
            'error': f'Invalid mode: {mode}. Use "hide" or "show"'
        }
    
    if not dimensions:
        return {
            'success': False,
            'error': 'dimensions list cannot be empty'
        }
    
    # 
    state = new_state.get('_pc_hidden_state')
    if not isinstance(state, dict):
        state = {'hidden': [], 'all_dimensions': None}
    
    hidden_set = set(state.get('hidden', []))
    
    #  transform  fold 
    transforms = new_state.get('transform', [])
    fold_index = -1
    fold_transform = None
    
    for i, t in enumerate(transforms):
        if isinstance(t, dict) and 'fold' in t:
            fold_index = i
            fold_transform = t
            break
    
    def _find_dimension_field(spec: Dict) -> Union[str, None]:
        enc = spec.get('encoding', {})
        x_enc = enc.get('x') if isinstance(enc, dict) else None
        if isinstance(x_enc, dict):
            field = x_enc.get('field')
            if isinstance(field, str) and field:
                return field
        for layer in spec.get('layer', []) if isinstance(spec.get('layer'), list) else []:
            if isinstance(layer, dict):
                layer_enc = layer.get('encoding', {})
                x_layer = layer_enc.get('x') if isinstance(layer_enc, dict) else None
                if isinstance(x_layer, dict):
                    field = x_layer.get('field')
                    if isinstance(field, str) and field:
                        return field
        return None

    def _collect_dimensions_from_values(values: List[Dict], field: str) -> List[str]:
        seen = set()
        ordered = []
        for row in values:
            if not isinstance(row, dict):
                continue
            val = row.get(field)
            if isinstance(val, str) and val not in seen:
                seen.add(val)
                ordered.append(val)
        return ordered

    def _find_all_dimensions(spec: Dict, field: str) -> List[str]:
        #  x.sort  x.scale.domain
        enc = spec.get('encoding', {})
        x_enc = enc.get('x') if isinstance(enc, dict) else None
        if isinstance(x_enc, dict):
            sort_vals = x_enc.get('sort')
            if isinstance(sort_vals, list) and sort_vals:
                return list(sort_vals)
            scale_domain = (x_enc.get('scale') or {}).get('domain')
            if isinstance(scale_domain, list) and scale_domain:
                return list(scale_domain)
        #  layer data.values 
        for layer in spec.get('layer', []) if isinstance(spec.get('layer'), list) else []:
            if isinstance(layer, dict):
                layer_data = layer.get('data', {})
                layer_values = layer_data.get('values') if isinstance(layer_data, dict) else None
                if isinstance(layer_values, list) and layer_values:
                    dims = _collect_dimensions_from_values(layer_values, field)
                    if dims:
                        return dims
        # 
        data = spec.get('data', {})
        values = data.get('values') if isinstance(data, dict) else None
        if isinstance(values, list) and values:
            return _collect_dimensions_from_values(values, field)
        return []

    def _update_x_encodings(obj: Any, field: str, visible: List[str]) -> None:
        if isinstance(obj, dict):
            enc = obj.get('encoding')
            if isinstance(enc, dict):
                x_enc = enc.get('x')
                if isinstance(x_enc, dict) and x_enc.get('field') == field:
                    x_enc['sort'] = list(visible)
                    scale = x_enc.get('scale')
                    if not isinstance(scale, dict):
                        scale = {}
                    scale['domain'] = list(visible)
                    x_enc['scale'] = scale
            for value in obj.values():
                _update_x_encodings(value, field, visible)
        elif isinstance(obj, list):
            for item in obj:
                _update_x_encodings(item, field, visible)

    def _pick_dimension_field_from_data(spec: Dict) -> Union[str, None]:
        data = spec.get('data', {})
        values = data.get('values') if isinstance(data, dict) else None
        if isinstance(values, list) and values:
            sample = values[0]
            if isinstance(sample, dict):
                for candidate in ['dimension', 'key', 'variable']:
                    if candidate in sample:
                        return candidate
        return None

    def _filter_layer_dimension_values(spec: Dict, field: str, visible: List[str]) -> None:
        for layer in spec.get('layer', []) if isinstance(spec.get('layer'), list) else []:
            if not isinstance(layer, dict):
                continue
            layer_data = layer.get('data', {})
            layer_values = layer_data.get('values') if isinstance(layer_data, dict) else None
            if isinstance(layer_values, list) and layer_values:
                filtered = [
                    row for row in layer_values
                    if isinstance(row, dict) and row.get(field) in visible
                ]
                if filtered:
                    layer['data']['values'] = filtered

    if fold_index < 0 or fold_transform is None:
        # ： fold， dimension 
        dim_field = _find_dimension_field(new_state)
        if not dim_field:
            dim_field = _pick_dimension_field_from_data(new_state)
        all_dims = _find_all_dimensions(new_state, dim_field) if dim_field else []
        if not dim_field or not all_dims:
            return {
                'success': False,
                'error': 'Cannot find dimension field or dimension list for non-fold parallel coordinates.'
            }
        if state.get('all_dimensions') is None:
            state['all_dimensions'] = list(all_dims)
        all_dims = state['all_dimensions']
    else:
        current_fold = list(fold_transform.get('fold', []))
        if state.get('all_dimensions') is None:
            state['all_dimensions'] = list(current_fold)
        all_dims = state['all_dimensions']
    
    if mode_lower == "hide":
        # 
        for dim in dimensions:
            hidden_set.add(dim)
        #  =  - 
        visible_dims = [d for d in all_dims if d not in hidden_set]
    else:
        # （）
        for dim in dimensions:
            hidden_set.discard(dim)
        visible_dims = [d for d in all_dims if d not in hidden_set]
    
    if not visible_dims:
        return {
            'success': False,
            'error': 'Cannot hide all dimensions. At least one dimension must remain visible.'
        }
    
    if fold_index >= 0 and fold_transform is not None:
        #  fold transform
        fold_transform['fold'] = visible_dims
        new_state['transform'][fold_index] = fold_transform
    else:
        #  fold： transform 
        if 'transform' not in new_state:
            new_state['transform'] = []
        visible_json = json.dumps(visible_dims)
        ff = dim_field.replace("\\", "\\\\").replace("'", "\\'")
        filter_expr = f"indexof({visible_json}, datum['{ff}']) >= 0"
        updated = False
        for t in new_state['transform']:
            if isinstance(t, dict) and t.get('_pc_hide_dimensions'):
                t['filter'] = filter_expr
                updated = True
                break
        if not updated:
            new_state['transform'].insert(0, {
                'filter': filter_expr,
                '_pc_hide_dimensions': True
            })
        _update_x_encodings(new_state, dim_field, visible_dims)
        _filter_layer_dimension_values(new_state, dim_field, visible_dims)
    
    # 
    state['hidden'] = list(hidden_set)
    new_state['_pc_hidden_state'] = state
    
    action = "Hidden" if mode_lower == "hide" else "Shown"
    return {
        'success': True,
        'operation': 'hide_dimensions',
        'vega_state': new_state,
        'hidden_dimensions': list(hidden_set),
        'visible_dimensions': visible_dims,
        'message': f'{action} dimensions: {dimensions}. Currently hidden: {list(hidden_set)}'
    }


def reset_hidden_dimensions(state: Dict) -> Dict[str, Any]:
    """
    ，。
    """
    new_state = copy.deepcopy(state)
    
    state = new_state.get('_pc_hidden_state')
    if not isinstance(state, dict) or state.get('all_dimensions') is None:
        return {
            'success': True,
            'operation': 'reset_hidden_dimensions',
            'vega_state': new_state,
            'message': 'No hidden dimensions to reset'
        }
    
    all_dims = state['all_dimensions']
    
    #  fold transform
    transforms = new_state.get('transform', [])
    for i, t in enumerate(transforms):
        if isinstance(t, dict) and 'fold' in t:
            t['fold'] = list(all_dims)
            new_state['transform'][i] = t
            break
    
    # 
    if '_pc_hidden_state' in new_state:
        del new_state['_pc_hidden_state']
    
    return {
        'success': True,
        'operation': 'reset_hidden_dimensions',
        'vega_state': new_state,
        'message': f'Reset to show all {len(all_dims)} dimensions'
    }


__all__ = [
    'highlight_cluster',
    'reorder_dimensions',
    'filter_by_category',
    'highlight_category',
    'hide_dimensions',
    'reset_hidden_dimensions',
]

for _fn_name in __all__:
    _fn = globals().get(_fn_name)
    if callable(_fn):
        globals()[_fn_name] = tool_output(_fn)
