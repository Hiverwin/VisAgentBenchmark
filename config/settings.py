"""
Application settings: OpenRouter VLM, system parameters, paths.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Global configuration."""

    # ==================== API ====================
    OPENROUTER_API_KEY: str = os.getenv('OPENROUTER_API_KEY', '')
    VLM_BASE_URL: str = os.getenv('VLM_BASE_URL', 'https://openrouter.ai/api/v1')
    VLM_MODEL: str = os.getenv('VLM_MODEL', 'google/gemini-3-flash-preview')

    # ==================== System ====================
    # <= 0 means unbounded iterations (stop only by model/controller signals)
    MAX_ITERATIONS: int = int(os.getenv('MAX_ITERATIONS', '0'))
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR: Path = Path(os.getenv('LOG_DIR', './logs'))

    # ==================== Session ====================
    SESSION_TIMEOUT: int = int(os.getenv('SESSION_TIMEOUT', '3600'))

    # ==================== Vega ====================
    VEGA_RENDERER: str = os.getenv('VEGA_RENDERER', 'canvas')
    IMAGE_FORMAT: str = os.getenv('IMAGE_FORMAT', 'png')

    # ==================== Paths ====================
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    PROMPTS_DIR: Path = PROJECT_ROOT / 'prompts'
    LOGS_DIR: Path = PROJECT_ROOT / 'logs'

    # ==================== VLM parameters ====================
    VLM_TEMPERATURE: float = 0
    VLM_MAX_TOKENS: int = 2000
    VLM_TOP_P: float = 0.9

    # ==================== Tool execution ====================
    TOOL_EXECUTION_TIMEOUT: int = 30  # seconds
    MAX_TOOL_RETRIES: int = 3

    # ==================== Logging ====================
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'
    APP_LOG_FILE: Path = PROJECT_ROOT / 'logs' / 'app.log'
    ERROR_LOG_FILE: Path = PROJECT_ROOT / 'logs' / 'error.log'

    # ==================== Agent modes ====================
    # <= 0 means unbounded iterations
    MAX_GOAL_ORIENTED_ITERATIONS: int = int(os.getenv('MAX_GOAL_ORIENTED_ITERATIONS', '0'))
    GOAL_ACHIEVEMENT_THRESHOLD: float = float(os.getenv('GOAL_ACHIEVEMENT_THRESHOLD', '0.9'))
    MAX_EXPLORATION_ITERATIONS: int = int(os.getenv('MAX_EXPLORATION_ITERATIONS', '0'))

    # ==================== Vega default size ====================
    VEGA_DEFAULT_WIDTH: int = int(os.getenv('VEGA_DEFAULT_WIDTH', '800'))
    VEGA_DEFAULT_HEIGHT: int = int(os.getenv('VEGA_DEFAULT_HEIGHT', '600'))

    # ==================== Vega rendering ====================
    VEGA_REQUIRE_CLI: bool = os.getenv('VEGA_REQUIRE_CLI', 'false').lower() in ('true', '1', 'yes')
    # If True, only vega-cli is used (no mock renderer).

    @classmethod
    def validate(cls) -> bool:
        """Validate required settings."""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set in environment variables")

        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)

        return True

    @classmethod
    def get_api_key(cls) -> str:
        """Return the API key or raise."""
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured")
        return cls.OPENROUTER_API_KEY

    @classmethod
    def get_model_name(cls) -> str:
        """Return configured model id."""
        return cls.VLM_MODEL

    @classmethod
    def to_dict(cls) -> dict:
        """Snapshot of non-secret settings for logging."""
        return {
            'api_key': cls.OPENROUTER_API_KEY[:10] + '...' if cls.OPENROUTER_API_KEY else 'Not set',
            'base_url': cls.VLM_BASE_URL,
            'model': cls.VLM_MODEL,
            'max_iterations': cls.MAX_ITERATIONS,
            'log_level': cls.LOG_LEVEL,
            'session_timeout': cls.SESSION_TIMEOUT,
            'vega_renderer': cls.VEGA_RENDERER,
        }


# Optional: validate on import
# Settings.validate()
