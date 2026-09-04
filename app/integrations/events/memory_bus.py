from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.integrations.events.base import DocumentEvent, EventPublisher

log = get_logger(__name__)


class InMemoryEventPublisher(EventPublisher):
    """Used by the test-suite and single-process demos.

    Events are pushed onto an ``asyncio.Queue``; a caller can drain and process
    them synchronously without Kafka.
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[DocumentEvent] = asyncio.Queue()
        self.published: list[DocumentEvent] = []

    async def start(self) -> None:  # noqa: D401
        return None

    async def stop(self) -> None:
        return None

    async def publish_document_event(self, event: DocumentEvent) -> None:
        self.published.append(event)
        await self.queue.put(event)
        log.info(
            "queued in-memory document event",
            fields={"document_id": event.document_id, "attempt": event.attempt},
        )
