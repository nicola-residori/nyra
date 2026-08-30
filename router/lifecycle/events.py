from __future__ import annotations
import asyncio
from dataclasses import dataclass
from shared.protocol.events import EventCategory, InteractionStateChanged, SessionClosedEvent, StateSnapshot


@dataclass(eq=False)
class Subscription:
    categories: set[EventCategory]
    queue: asyncio.Queue


class InteractionEventBroker:
    def __init__(self, queue_size: int = 100):
        self.queue_size = queue_size
        self.subscriptions: set[Subscription] = set()
        self._states: dict[str | None, StateSnapshot] = {}

    async def subscribe(self, categories: set[EventCategory]) -> Subscription:
        sub = Subscription(categories=set(categories), queue=asyncio.Queue(maxsize=self.queue_size))
        self.subscriptions.add(sub)
        return sub

    async def unsubscribe(self, subscription: Subscription) -> None:
        self.subscriptions.discard(subscription)

    async def _publish(self, category: EventCategory, event) -> None:
        dead = []
        for sub in tuple(self.subscriptions):
            if category not in sub.categories:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(sub)
        for sub in dead:
            self.subscriptions.discard(sub)

    async def publish_state(self, event: InteractionStateChanged) -> None:
        source_id = event.source.id if event.source else None
        self._states[source_id] = StateSnapshot(
            source_id=source_id,
            state=event.state,
            timestamp=event.timestamp,
            session_id=event.session_id,
            request_id=event.request_id,
            trace_id=event.trace_id,
        )
        await self._publish(EventCategory.INTERACTION_STATE, event)

    async def publish_session_closed(self, event: SessionClosedEvent) -> None:
        await self._publish(EventCategory.SESSION, event)

    def snapshot(self, source_id: str | None = None) -> list[StateSnapshot]:
        if source_id is not None:
            state = self._states.get(source_id)
            return [state] if state else []
        return list(self._states.values())
