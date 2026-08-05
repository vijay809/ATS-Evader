"""In-process event delivery for decoupled runtime components."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

EventHandler = Callable[["RuntimeEvent"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Async, local event bus. Handler failures are isolated from each other."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            self._handlers[topic].remove(handler)

        return unsubscribe

    async def publish(self, event: RuntimeEvent) -> None:
        for handler in tuple(self._handlers[event.topic]):
            await handler(event)
