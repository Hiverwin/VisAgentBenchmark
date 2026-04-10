"""Configuration package."""

from .settings import Settings
from .chart_types import ChartType
from .intent_types import IntentType


def validate_config() -> list:
    """
    Validate configuration.

    Returns:
        List of error strings; empty means OK.
    """
    errors = []

    if not Settings.OPENROUTER_API_KEY:
        errors.append("OPENROUTER_API_KEY is not set")

    Settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    return errors


__all__ = ['Settings', 'ChartType', 'IntentType', 'validate_config']
