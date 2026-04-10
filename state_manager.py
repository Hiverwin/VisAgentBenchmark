import copy
import functools
from contextvars import ContextVar
from typing import Any, Dict, Tuple


_current_data: ContextVar[Any] = ContextVar("_current_data", default=None)


class DataStore:
    """Request-local data context for state-only tools."""

    @staticmethod
    def set(data: Any) -> None:
        _current_data.set(data)

    @staticmethod
    def get() -> Any:
        return _current_data.get()

    @staticmethod
    def get_values() -> Any:
        data = _current_data.get()
        if isinstance(data, dict):
            return data.get("values", [])
        if isinstance(data, list):
            return data
        return []


class StateManager:
    @staticmethod
    def split(vega_spec: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
        state = {k: v for k, v in vega_spec.items() if k != "data"}
        data = vega_spec.get("data")
        return state, data

    @staticmethod
    def reconstruct(state: Dict[str, Any], data: Any = None) -> Dict[str, Any]:
        spec = dict(state)
        if data is not None:
            spec["data"] = data
        return spec


def tool_output(func):
    """
    Normalize tool IO:
    - input may be full vega_spec or pure state
    - tool returns `vega_state`
    - wrapper emits `state` + full `vega_spec`
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        call_args = list(args)
        call_kwargs = dict(kwargs)

        if "vega_spec" in call_kwargs and isinstance(call_kwargs["vega_spec"], dict):
            incoming = call_kwargs.pop("vega_spec")
            state, data = StateManager.split(incoming) if "data" in incoming else (incoming, DataStore.get())
            if data is not None:
                DataStore.set(data)
            call_kwargs["state"] = state
        elif "state" in call_kwargs and isinstance(call_kwargs["state"], dict):
            incoming = call_kwargs["state"]
            state, data = StateManager.split(incoming) if "data" in incoming else (incoming, DataStore.get())
            if data is not None:
                DataStore.set(data)
            call_kwargs["state"] = state
        elif call_args and isinstance(call_args[0], dict):
            incoming = call_args[0]
            state, data = StateManager.split(incoming) if "data" in incoming else (incoming, DataStore.get())
            if data is not None:
                DataStore.set(data)
            call_args[0] = state

        result = func(*call_args, **call_kwargs)
        if not isinstance(result, dict) or not result.get("success"):
            return result
        if "vega_state" not in result:
            return result

        new_state = result.pop("vega_state")
        result["state"] = copy.deepcopy(new_state)
        if isinstance(new_state, dict) and "data" in new_state:
            result["vega_spec"] = new_state
            return result

        data = DataStore.get()
        result["vega_spec"] = StateManager.reconstruct(new_state, data) if data is not None else new_state
        return result

    return wrapper
