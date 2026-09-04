from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.exceptions import UpstreamError
from app.core.logging import get_logger
from app.core.metrics import llm_requests_total
from app.integrations.llm.base import LLMClient, LLMResponse

log = get_logger(__name__)


class OpenAICompatibleLLMClient(LLMClient):
    provider = "openai"

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        self.model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # retries are handled by the processing pipeline
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                ),
                timeout=self._timeout + 5,
            )
        except asyncio.TimeoutError as exc:
            llm_requests_total.labels(provider=self.provider, outcome="timeout").inc()
            raise UpstreamError("LLM request timed out") from exc
        except Exception as exc:  # noqa: BLE001
            llm_requests_total.labels(provider=self.provider, outcome="error").inc()
            raise UpstreamError(f"LLM request failed: {exc}") from exc

        content = (resp.choices[0].message.content or "").strip()
        llm_requests_total.labels(provider=self.provider, outcome="success").inc()
        return LLMResponse(content=content, provider=self.provider, model=self.model)
