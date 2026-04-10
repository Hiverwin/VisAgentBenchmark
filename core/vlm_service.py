
from typing import Dict, List, Any

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config.settings import Settings
from core.utils import app_logger, extract_json_from_text


class VLMService:
    """Vision-language model call service."""

    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and Settings.OPENROUTER_API_KEY:
            self.client = OpenAI(
                api_key=Settings.OPENROUTER_API_KEY,
                base_url=Settings.VLM_BASE_URL
            )
        self.model = Settings.VLM_MODEL
        self.max_tokens = Settings.VLM_MAX_TOKENS
        self.temperature = Settings.VLM_TEMPERATURE
        app_logger.info(f"VLM Service initialized: {self.model}")

    def call(self, messages: List[Dict], system_prompt: str = None,
             expect_json: bool = False) -> Dict:
        """Invoke the VLM."""
        if not OPENAI_AVAILABLE:
            return {
                "success": False,
                "error": "openai package is not installed; install dependency to enable VLM calls",
            }
        if self.client is None:
            return {
                "success": False,
                "error": "OPENROUTER_API_KEY is not configured",
            }

        try:
            api_messages = self._prepare_messages(messages, system_prompt)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            content = self._extract_text_from_response(response)
            app_logger.info(f"VLM raw output (first 500 chars): {content[:500]}")

            result = {"success": True, "content": content}
            if expect_json:
                result["parsed_json"] = extract_json_from_text(content)
            return result
        except Exception as e:
            app_logger.error(f"VLM call failed: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _prepare_messages(self, messages: List, system_prompt: str = None) -> List:
        """Build OpenAI-compatible chat messages."""
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", [])
            if isinstance(content, str):
                api_messages.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                api_parts = []
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if "text" in part:
                        api_parts.append({
                            "type": "text",
                            "text": str(part.get("text", "")),
                        })
                    elif "image" in part:
                        api_parts.append({
                            "type": "image_url",
                            "image_url": {"url": str(part.get("image", ""))},
                        })
                if api_parts:
                    api_messages.append({"role": role, "content": api_parts})
                    continue

            api_messages.append({"role": role, "content": str(content)})
        return api_messages

    def _extract_text_from_response(self, response: Any) -> str:
        """Extract text from an OpenAI-compatible chat response."""
        try:
            message_content = response.choices[0].message.content
        except Exception:
            return ""

        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            parts = []
            for item in message_content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(message_content or "")

    def call_with_image(self, text: str, image_base64: str,
                       system_prompt: str = None, expect_json: bool = False):
        """Convenience: text plus one image."""
        messages = [{
            "role": "user",
            "content": [
                {"text": text},
                {"image": f"data:image/png;base64,{image_base64}"}
            ]
        }]
        return self.call(messages, system_prompt, expect_json)

    def call_text_only(self, text: str, system_prompt: str = None,
                       expect_json: bool = False):
        """Convenience: text only."""
        messages = [{"role": "user", "content": [{"text": text}]}]
        return self.call(messages, system_prompt, expect_json)


_vlm_service = None

def get_vlm_service() -> VLMService:
    """Return the global VLMService singleton."""
    global _vlm_service
    if _vlm_service is None:
        _vlm_service = VLMService()
    return _vlm_service
