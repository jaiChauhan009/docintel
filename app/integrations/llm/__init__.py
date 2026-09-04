from __future__ import annotations

from app.core.config import settings
from app.integrations.llm.base import LLMClient, LLMResponse
from app.integrations.llm.fake_client import FakeLLMClient


def get_llm_client() -> LLMClient:
    if settings.llm_provider.lower() == "openai":
        from app.integrations.llm.openai_client import OpenAICompatibleLLMClient

        return OpenAICompatibleLLMClient()
    return FakeLLMClient()


__all__ = ["LLMClient", "LLMResponse", "FakeLLMClient", "get_llm_client"]
