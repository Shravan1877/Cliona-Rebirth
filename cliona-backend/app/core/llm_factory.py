"""Model swapping. Only settings.LLM_MODEL_ID changes to swap models — no code change."""

from langchain_openai import ChatOpenAI

from app.core.config import settings


class LLMFactory:
    @staticmethod
    def get_llm(streaming: bool = False) -> ChatOpenAI:
        raise NotImplementedError("Phase 1")
