from __future__ import annotations

import json

from app.core.config import settings
from app.core.exceptions import UpstreamError
from app.core.logging import get_logger
from app.integrations.events.base import DocumentEvent, EventPublisher

log = get_logger(__name__)


class KafkaEventPublisher(EventPublisher):
    def __init__(self) -> None:
        self._producer = None
        self._topic = settings.kafka_document_topic

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            enable_idempotence=True,
            acks="all",
            linger_ms=20,
        )
        await self._producer.start()
        log.info("kafka producer started", fields={"topic": self._topic})

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish_document_event(self, event: DocumentEvent) -> None:
        if self._producer is None:
            raise UpstreamError("kafka producer not started")
        payload = json.dumps(event.to_dict()).encode("utf-8")
        try:
            await self._producer.send_and_wait(
                self._topic, value=payload, key=event.document_id.encode("utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"failed to publish kafka event: {exc}") from exc
        log.info(
            "published document event",
            fields={"document_id": event.document_id, "event": event.event, "attempt": event.attempt},
        )
