"""Model swapping. Only settings.LLM_MODEL_ID changes to swap models — no code change.

Only gateway: OpenRouter, via langchain_openai.ChatOpenAI (§2). No direct
provider SDKs.
"""

from typing import Optional

from langchain_openai import ChatOpenAI

from app.core.config import settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter's optional attribution headers (openrouter.ai/docs -> app attribution).
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://cliona.app",
    "X-Title": "Cliona",
}


class LLMFactory:
    @staticmethod
    def get_llm(model_name: Optional[str] = None, streaming: bool = True) -> ChatOpenAI:
        return ChatOpenAI(
            model=model_name or settings.LLM_MODEL_ID,
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            temperature=0.85,
            max_tokens=1024,
            timeout=60,
            streaming=streaming,
            default_headers=OPENROUTER_HEADERS,
        )
