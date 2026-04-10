"""Shared helpers: logging, images, JSON, Vega data access."""
from .logger import setup_logger, app_logger, error_logger
from .image_utils import encode_image_to_base64, decode_base64_to_image, create_data_url
from .json_utils import safe_json_loads, safe_json_dumps, extract_json_from_text
from typing import Dict, List, Any


def get_spec_data_values(spec: Dict) -> List[Dict[str, Any]]:
    """
    Return data rows from a Vega or Vega-Lite spec.

    - Vega-Lite: data is an object ``{"values": [...]}``
    - Vega: data is a list of sources ``[{"name": "...", "values": [...]}, ...]``

    Returns:
        List of row dicts (Vega: first source that has ``values``).
    """
    data = spec.get("data", {})
    if isinstance(data, list):
        for d in data:
            if isinstance(d, dict) and d.get("values"):
                return d.get("values", [])
        return []
    else:
        return data.get("values", []) if isinstance(data, dict) else []


def get_spec_data_count(spec: Dict) -> int:
    """Total number of data points in the spec."""
    data = spec.get("data", {})
    if isinstance(data, list):
        return sum(len(d.get("values", [])) for d in data if isinstance(d, dict))
    else:
        return len(data.get("values", [])) if isinstance(data, dict) else 0


def is_vega_full_spec(spec: Dict) -> bool:
    """True if this is a full Vega spec (not Vega-Lite)."""
    schema = spec.get("$schema", "")
    if "vega-lite" in schema.lower():
        return False
    if "/vega/" in schema.lower() or "vega/v" in schema.lower():
        return True
    if "signals" in spec or ("scales" in spec and "encoding" not in spec):
        return True
    if isinstance(spec.get("data"), list):
        return True
    return False


__all__ = [
    'setup_logger', 'app_logger', 'error_logger',
    'encode_image_to_base64', 'decode_base64_to_image', 'create_data_url',
    'safe_json_loads', 'safe_json_dumps', 'extract_json_from_text',
    'get_spec_data_values', 'get_spec_data_count', 'is_vega_full_spec',
]
