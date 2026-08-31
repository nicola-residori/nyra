from shared.protocol.events import InteractionState, EventCategory, InteractionStateChanged, SessionClosedEvent, EventSubscription, StateSnapshot
from shared.protocol.requests import CloseReason
from router.observability.ids import generate_request_id, generate_session_id, generate_trace_id


def test_interaction_state_contract_serializes_correlation():
    event = InteractionStateChanged(
        state=InteractionState.PROCESSING_GLOBAL,
        source={"id":"speaker-a","area":"living-room"},
        session_id=generate_session_id(),
        request_id=generate_request_id(),
        trace_id=generate_trace_id(),
    )
    data = event.model_dump(mode="json")
    assert data["event"] == "INTERACTION_STATE_CHANGED"
    assert data["category"] == "interaction_state"
    assert data["state"] == "PROCESSING_GLOBAL"


def test_session_closed_contract_has_stable_reason():
    event = SessionClosedEvent(
        session_id=generate_session_id(),
        request_id=generate_request_id(),
        trace_id=generate_trace_id(),
        close_reason=CloseReason.DIRECT_COMMAND,
    )
    assert event.event == "SESSION_CLOSED"
    assert event.close_reason is CloseReason.DIRECT_COMMAND


def test_subscription_and_snapshot_contracts():
    sub = EventSubscription(categories={EventCategory.INTERACTION_STATE})
    assert EventCategory.INTERACTION_STATE in sub.categories
    snap = StateSnapshot(source_id="speaker-a", state=InteractionState.PROCESSING_LOCAL)
    assert snap.source_id == "speaker-a"


def test_events_reject_unprefixed_correlation_ids():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InteractionStateChanged(
            state=InteractionState.PROCESSING_LOCAL,
            session_id="550e8400-e29b-41d4-a716-446655440000",
        )
