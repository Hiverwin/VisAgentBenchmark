"""
Prompt manager: load, assemble, and cache prompt templates.
"""

from pathlib import Path
from typing import Dict, Optional
from config.chart_types import ChartType
from config.intent_types import IntentType


class PromptManager:
    """Loads and assembles prompt templates."""

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize the prompt manager.

        Args:
            prompts_dir: Directory containing prompt files; defaults to this package's prompts dir.
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent

        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}

    def _load_prompt_file(self, file_path: Path) -> str:
        """
        Load a prompt file.

        Args:
            file_path: Path to the prompt file.

        Returns:
            File contents as a string.
        """
        cache_key = str(file_path)

        if cache_key in self._cache:
            return self._cache[cache_key]

        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self._cache[cache_key] = content

        return content

    def get_base_system_role(self) -> str:
        """Load the base system role prompt."""
        file_path = self.prompts_dir / 'base' / 'system_role.txt'
        return self._load_prompt_file(file_path)

    def get_chitchat_prompt(self) -> str:
        """Load the chitchat mode prompt."""
        file_path = self.prompts_dir / 'base' / 'chitchat.txt'
        return self._load_prompt_file(file_path)

    def get_intent_classifier_prompt(self) -> str:
        """Load the intent-classifier prompt."""
        file_path = self.prompts_dir / 'intent_recognition' / 'intent_classifier.txt'
        return self._load_prompt_file(file_path)

    def get_chart_skill_prompt(self, chart_type: ChartType) -> str:
        """
        Load chart-type skill prompt (intent -> tool chain).

        Args:
            chart_type: Chart type enum.

        Returns:
            Skill prompt text, or empty string if none.
        """
        chart_file_mapping = {
            ChartType.BAR_CHART: 'bar_chart.txt',
            ChartType.LINE_CHART: 'line_chart.txt',
            ChartType.SCATTER_PLOT: 'scatter_plot.txt',
            ChartType.PARALLEL_COORDINATES: 'parallel_coordinates.txt',
            ChartType.HEATMAP: 'heatmap.txt',
            ChartType.SANKEY_DIAGRAM: 'sankey_diagram.txt',
        }

        filename = chart_file_mapping.get(chart_type)
        if not filename:
            return ""

        file_path = self.prompts_dir / 'chart_skills' / filename
        if not file_path.exists():
            return ""
        return self._load_prompt_file(file_path)

    def get_goal_oriented_prompt(self) -> str:
        """Load goal-oriented mode prompt."""
        file_path = self.prompts_dir / 'modes' / 'goal_oriented.txt'
        return self._load_prompt_file(file_path)

    def get_autonomous_exploration_prompt(self) -> str:
        """Load autonomous exploration mode prompt."""
        file_path = self.prompts_dir / 'modes' / 'autonomous_exploration.txt'
        return self._load_prompt_file(file_path)

    def get_benchmark_answer_instruction(self) -> str:
        """Load benchmark answer-format instructions."""
        file_path = self.prompts_dir / 'modes' / 'benchmark_answer_instruction.txt'
        return self._load_prompt_file(file_path)

    def assemble_system_prompt(
        self,
        chart_type: Optional[ChartType] = None,
        intent_type: Optional[IntentType] = None,
        mode: Optional[str] = None,
        include_tools: bool = False,
        tools_description: str = "",
        benchmark_mode: bool = False
    ) -> str:
        """
        Assemble the full system prompt.

        Args:
            chart_type: Current chart type.
            intent_type: Intent type.
            mode: Mode string ("goal_oriented" or "autonomous_exploration"); maps to intent_type if set.
            include_tools: Whether to append tool descriptions.
            tools_description: Serialized tool descriptions.
            benchmark_mode: If True, append ANSWER field requirements.

        Returns:
            Combined system prompt string.
        """
        if mode and not intent_type:
            if mode == "goal_oriented":
                intent_type = IntentType.EXPLICIT_ANALYSIS
            elif mode == "autonomous_exploration":
                intent_type = IntentType.VAGUE_EXPLORATION

        parts = []

        parts.append(self.get_base_system_role())

        if chart_type and chart_type != ChartType.UNKNOWN:
            skill_prompt = self.get_chart_skill_prompt(chart_type)
            if skill_prompt:
                parts.append("\n\n" + "="*60)
                parts.append("# Chart-type skill guidance")
                parts.append("="*60)
                parts.append(skill_prompt)

        if intent_type:
            if intent_type == IntentType.CHITCHAT:
                parts.append("\n\n" + "="*60)
                parts.append("# Mode: chitchat")
                parts.append("="*60)
                parts.append(self.get_chitchat_prompt())

            elif intent_type == IntentType.EXPLICIT_ANALYSIS:
                parts.append("\n\n" + "="*60)
                parts.append("# Mode: goal-oriented analysis")
                parts.append("="*60)
                parts.append(self.get_goal_oriented_prompt())

            elif intent_type == IntentType.VAGUE_EXPLORATION:
                parts.append("\n\n" + "="*60)
                parts.append("# Mode: autonomous exploration")
                parts.append("="*60)
                parts.append(self.get_autonomous_exploration_prompt())

        if include_tools and tools_description:
            parts.append("\n\n" + "="*60)
            parts.append("# Available tools")
            parts.append("="*60)
            parts.append(tools_description)

        if benchmark_mode:
            parts.append("\n\n" + "="*60)
            parts.append("# Benchmark answer format")
            parts.append("="*60)
            parts.append(self.get_benchmark_answer_instruction())

        full_prompt = "\n".join(parts)

        return full_prompt

    def get_intent_recognition_prompt(
        self,
        user_query: str,
        chart_type: Optional[ChartType] = None
    ) -> str:
        """
        Build the full prompt for intent recognition.

        Args:
            user_query: User message.
            chart_type: Current chart type, if known.

        Returns:
            Intent recognition prompt text.
        """
        parts = []

        parts.append(self.get_intent_classifier_prompt())

        parts.append("\n\n" + "="*60)
        parts.append("# Context")
        parts.append("="*60)

        if chart_type and chart_type != ChartType.UNKNOWN:
            parts.append(f"Current chart type: {chart_type.value}")

        parts.append(f"\nUser query: {user_query}")

        parts.append(
            "\nAnalyze the intent of the user query above and respond with the required JSON format."
        )

        return "\n".join(parts)

    def clear_cache(self):
        """Clear the prompt file cache."""
        self._cache.clear()

    def preload_all_prompts(self):
        """Preload common prompts into the cache."""
        self.get_base_system_role()
        self.get_chitchat_prompt()
        self.get_intent_classifier_prompt()

        for chart_type in ChartType:
            if chart_type != ChartType.UNKNOWN:
                try:
                    self.get_chart_skill_prompt(chart_type)
                except FileNotFoundError:
                    pass

        self.get_goal_oriented_prompt()
        self.get_autonomous_exploration_prompt()


_prompt_manager = None


def get_prompt_manager() -> PromptManager:
    """Return the global PromptManager singleton."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
