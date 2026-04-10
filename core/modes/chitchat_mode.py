
"""Chitchat mode: lightweight conversational replies."""

from typing import Dict, Any, Optional, Callable

from core.utils import app_logger
from core.vlm_service import get_vlm_service
from prompts import get_prompt_manager


class ChitchatMode:
    """Handles non-analytical chat turns."""

    def __init__(self):
        self.vlm = get_vlm_service()
        self.prompt_mgr = get_prompt_manager()

    def execute(
        self,
        user_query: str,
        image_base64: str,
        session: Dict[str, Any],
        event_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Run a chitchat turn (multi-turn messages when history exists)."""
        messages = session.get("messages", [])

        # Prior turns from context
        if not messages:
            messages = []

        # Build user message
        user_content = [{"text": user_query}]
        if image_base64:
            user_content.append({"image": f"data:image/png;base64,{image_base64}"})
        messages.append({"role": "user", "content": user_content})

        system_prompt = self.prompt_mgr.get_chitchat_prompt()

        # VLM call
        response = self.vlm.call(messages, system_prompt=system_prompt)

        if response.get("success"):
            assistant_text = response.get("content", "")
            # Append assistant message
            messages.append({
                "role": "assistant",
                "content": [{"text": assistant_text}],
            })
            # Save to context
            session["messages"] = messages

            return {
                "success": True,
                "mode": "chitchat",
                "response": assistant_text,
                "raw_output": response.get("content", ""),  # same as response for chitchat
            }

        return {
            "success": False,
            "error": response.get("error", "VLM call failed"),
            "mode": "chitchat",
        }
