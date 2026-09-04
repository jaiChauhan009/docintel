from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str


class LLMClient(abc.ABC):
    """OpenAI-compatible chat client.

    ``complete_json`` MUST return the raw assistant message text. The caller treats
    it as untrusted and is responsible for parsing + schema validation.
    """

    provider: str = "base"
    model: str = "unknown"

    @abc.abstractmethod
    async def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        ...
