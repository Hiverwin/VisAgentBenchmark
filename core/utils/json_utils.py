"""JSON helpers."""
import json
from typing import Any

def safe_json_loads(json_str: str, default=None) -> Any:
    """Parse JSON or return default."""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return default

def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Serialize to JSON or return '{}'."""
    try:
        return json.dumps(obj, ensure_ascii=False, **kwargs)
    except Exception:
        return "{}"

def extract_json_from_text(text: str) -> dict:
    """Extract a JSON object from mixed VLM output."""
    start_idx = text.find('{')
    if start_idx != -1:
        end_idx = text.rfind('}')
        if end_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx:end_idx+1]
            result = safe_json_loads(json_str)
            if result and isinstance(result, dict):
                return result

    start_idx = text.find('[')
    if start_idx != -1:
        end_idx = text.rfind(']')
        if end_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx:end_idx+1]
            result = safe_json_loads(json_str)
            if result:
                return {}

    return {}
