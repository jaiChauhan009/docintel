from __future__ import annotations

from app.core.config import settings
from app.integrations.events.base import DocumentEvent, EventPublisher
from app.integrations.events.memory_bus import InMemoryEventPublisher

_singleton: EventPublisher | None = None


def build_event_publisher() -> EventPublisher:
    if settings.event_bus.lower() == "kafka":
        from app.integrations.events.kafka_bus import KafkaEventPublisher

        return KafkaEventPublisher()
    return InMemoryEventPublisher()


def get_event_publisher() -> EventPublisher:
    """Process-wide singleton used by the API layer."""
    global _singleton
    if _singleton is None:
        _singleton = build_event_publisher()
    return _singleton


def set_event_publisher(publisher: EventPublisher | None) -> None:
    """Test hook."""
    global _singleton
    _singleton = publisher


__all__ = [
    "DocumentEvent",
    "EventPublisher",
    "InMemoryEventPublisher",
    "build_event_publisher",
    "get_event_publisher",
    "set_event_publisher",
]
