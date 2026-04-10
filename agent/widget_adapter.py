"""Widget adapter scaffolding for runtime decoupling."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class WidgetSnapshot:
    """In-memory widget snapshot used by runtime adapters."""

    spec: Dict[str, Any]
    state: Dict[str, Any]
    image_base64: str


class BaseWidgetAdapter:
    """Base adapter to unify widget state/spec access patterns."""

    def __init__(self, snapshot: WidgetSnapshot):
        self.snapshot = snapshot

    def get_spec(self) -> Dict[str, Any]:
        return self.snapshot.spec

    def get_state(self) -> Dict[str, Any]:
        return self.snapshot.state

    def get_image(self) -> str:
        return self.snapshot.image_base64

    def update(self, *, spec: Dict[str, Any], state: Dict[str, Any], image_base64: str) -> None:
        self.snapshot = WidgetSnapshot(spec=spec, state=state, image_base64=image_base64)

    def get_observation(self, user_query: str) -> Dict[str, Any]:
        return {
            "user_query": user_query,
            "widget_state": self.get_state(),
            "rendered_view": self.get_image(),
        }


class StaticToolRegistryAdapter:
    """Small helper that wraps a static tool registry list."""

    def __init__(self, tools: List[Dict[str, Any]]):
        self._tools = tools

    def list_tools(self) -> List[Dict[str, Any]]:
        return self._tools
