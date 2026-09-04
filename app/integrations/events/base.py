from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentEvent:
    document_id: str
    user_id: str
    event: str = "document.uploaded"
    attempt: int = 1
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "document_id": self.document_id,
            "user_id": self.user_id,
            "attempt": self.attempt,
            "request_id": self.request_id,
            **self.extra,
        }


class EventPublisher(abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def publish_document_event(self, event: DocumentEvent) -> None: ...
