import asyncio
import pytest
from router.lifecycle.events import InteractionEventBroker
from shared.protocol.events import EventCategory, InteractionState, InteractionStateChanged, SessionClosedEvent
from shared.protocol.requests import CloseReason


@pytest.mark.asyncio
async def test_broker_publishes_filters_and_resynchronizes_state():
    broker = InteractionEventBroker(queue_size=2)
    state_sub = await broker.subscribe({EventCategory.INTERACTION_STATE})
    session_sub = await broker.subscribe({EventCategory.SESSION})
    event = InteractionStateChanged(state=InteractionState.MEMORY, source={"id":"speaker-a","area":"living-room"})
    await broker.publish_state(event)
    assert (await asyncio.wait_for(state_sub.queue.get(), .2)).state is InteractionState.MEMORY
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(session_sub.queue.get(), .02)
    snaps = broker.snapshot("speaker-a")
    assert len(snaps) == 1 and snaps[0].state is InteractionState.MEMORY


@pytest.mark.asyncio
async def test_broker_session_closed_and_unsubscribe():
    broker = InteractionEventBroker(queue_size=2)
    sub = await broker.subscribe({EventCategory.SESSION})
    await broker.publish_session_closed(SessionClosedEvent(close_reason=CloseReason.DIRECT_COMMAND))
    assert (await asyncio.wait_for(sub.queue.get(), .2)).event == "SESSION_CLOSED"
    await broker.unsubscribe(sub)
    assert sub not in broker.subscriptions


@pytest.mark.asyncio
async def test_slow_subscriber_is_dropped_instead_of_blocking():
    broker = InteractionEventBroker(queue_size=1)
    sub = await broker.subscribe({EventCategory.INTERACTION_STATE})
    await broker.publish_state(InteractionStateChanged(state=InteractionState.PROCESSING))
    await broker.publish_state(InteractionStateChanged(state=InteractionState.MEMORY))
    assert sub not in broker.subscriptions
