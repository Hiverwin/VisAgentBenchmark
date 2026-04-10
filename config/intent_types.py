"""
Intent type enum and metadata for user-intent routing.
"""

from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass


class IntentType(Enum):
    """User intent categories."""

    CHITCHAT = "chitchat"
    EXPLICIT_ANALYSIS = "explicit_analysis"
    VAGUE_EXPLORATION = "vague_exploration"
    UNKNOWN = "unknown"

    def __str__(self):
        return self.value

    @classmethod
    def from_string(cls, intent: str) -> 'IntentType':
        """Parse enum from string."""
        intent_lower = intent.lower().replace(' ', '_').replace('-', '_')
        for it in cls:
            if it.value == intent_lower:
                return it
        return cls.UNKNOWN

    def is_analytical(self) -> bool:
        return self in [IntentType.EXPLICIT_ANALYSIS, IntentType.VAGUE_EXPLORATION]

    def is_chitchat(self) -> bool:
        return self == IntentType.CHITCHAT


@dataclass
class IntentConfig:
    """Display and routing metadata for an intent."""
    name: str
    display_name: str
    description: str
    execution_mode: str  # 'direct', 'goal_oriented', 'autonomous_exploration'
    requires_tools: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'execution_mode': self.execution_mode,
            'requires_tools': self.requires_tools
        }


INTENT_CONFIGS = {
    IntentType.CHITCHAT: IntentConfig(
        name="chitchat",
        display_name="Chitchat",
        description="Casual conversation, greetings, or non-analytical questions",
        execution_mode="direct",
        requires_tools=False
    ),

    IntentType.EXPLICIT_ANALYSIS: IntentConfig(
        name="explicit_analysis",
        display_name="Explicit analysis",
        description="Clear analytical goal and concrete manipulation requests",
        execution_mode="goal_oriented",
        requires_tools=True
    ),

    IntentType.VAGUE_EXPLORATION: IntentConfig(
        name="vague_exploration",
        display_name="Open-ended exploration",
        description="Unclear goal; system should explore the data autonomously",
        execution_mode="autonomous_exploration",
        requires_tools=True
    )
}


def get_intent_config(intent_type: IntentType) -> IntentConfig:
    return INTENT_CONFIGS.get(intent_type, None)


def get_execution_mode(intent_type: IntentType) -> str:
    config = get_intent_config(intent_type)
    return config.execution_mode if config else "direct"


def requires_tool_support(intent_type: IntentType) -> bool:
    config = get_intent_config(intent_type)
    return config.requires_tools if config else False


# Optional keyword hints for auxiliary matching (English)
INTENT_KEYWORDS = {
    IntentType.CHITCHAT: [
        "hi", "hello", "thanks", "bye", "how are you", "what is", "introduce",
        "what can you do"
    ],

    IntentType.EXPLICIT_ANALYSIS: [
        "filter", "zoom", "highlight", "sort", "show", "find", "view", "compare",
        "2020 to 2022", "top", "max", "min"
    ],

    IntentType.VAGUE_EXPLORATION: [
        "what", "how", "help me look", "analyze", "interesting", "insights",
        "discover", "pattern", "trend", "feature", "explore", "understand"
    ]
}


def get_intent_keywords(intent_type: IntentType) -> list:
    return INTENT_KEYWORDS.get(intent_type, [])
