"""Kafka consumer worker.

Run with:  python -m app.workers.consumer

Responsibilities:
  * consume ``document.processing`` events and run the extraction pipeline
  * periodically flush due webhook deliveries (exponential-backoff retries)
"""
from __future__ import annotations

import asyncio
import json
import signal

from app.core.config import settings
from app.core.logging import bind_context, clear_context, configure_logging, get_logger
from app.db.session import SessionFactory
from app.integrations.events import get_event_publisher
from app.services.processing_service import DocumentProcessor
from app.services.webhook_service import WebhookService

configure_logging(settings.log_level)
log = get_logger("app.worker")

_shutdown = asyncio.Event()


async def _handle_message(raw_value: bytes) -> None:
    clear_context()
    try:
        event = json.loads(raw_value.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        log.error("dropping unparseable message", fields={"error": str(exc)})
        return

    bind_context(document_id=event.get("document_id"), request_id=event.get("request_id"))
    async with SessionFactory() as session:
        processor = DocumentProcessor(session, publisher=get_event_publisher())
        try:
            outcome = await processor.process_event(event)
            log.info("processed event", fields={"outcome": outcome})
        except Exception:  # noqa: BLE001 - never let one bad message kill the loop
            log.exception("unhandled error while processing event")
            await session.rollback()


async def _webhook_retry_loop() -> None:
    interval = max(settings.webhook_backoff_base_seconds, 5)
    while not _shutdown.is_set():
        try:
            async with SessionFactory() as session:
                svc = WebhookService(session)
                processed = await svc.process_due(limit=100)
                await session.commit()
                if processed:
                    log.info("flushed webhook deliveries", fields={"count": processed})
        except Exception:  # noqa: BLE001
            log.exception("webhook retry loop error")
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def _consume() -> None:
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        settings.kafka_document_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_interval_ms=600_000,
    )
    publisher = get_event_publisher()

    # Retry with backoff until Kafka is reachable (compose start ordering).
    for attempt in range(1, 31):
        try:
            await consumer.start()
            await publisher.start()
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("kafka not ready, retrying", fields={"attempt": attempt, "error": str(exc)})
            await asyncio.sleep(min(attempt * 2, 20))
    else:
        raise RuntimeError("could not connect to Kafka")

    try:
        from prometheus_client import start_http_server

        start_http_server(9100)
        log.info("worker metrics exposed on :9100/metrics")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not start worker metrics server", fields={"error": str(exc)})

    log.info("worker consuming", fields={"topic": settings.kafka_document_topic,
                                         "group": settings.kafka_consumer_group})
    retry_task = asyncio.create_task(_webhook_retry_loop())
    try:
        while not _shutdown.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=10)
            for _tp, messages in batch.items():
                for message in messages:
                    await _handle_message(message.value)
            if batch:
                await consumer.commit()
    finally:
        _shutdown.set()
        retry_task.cancel()
        await consumer.stop()
        await publisher.stop()
        log.info("worker stopped")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown.set)
        except NotImplementedError:  # pragma: no cover - windows
            pass


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        loop.run_until_complete(_consume())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
