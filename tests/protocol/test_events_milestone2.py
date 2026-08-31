from shared.protocol.events import (
    EventCategory,
    IdentityFeedback,
    IdentityFeedbackEvent,
    InteractionState,
)
from shared.protocol.ids import new_request_id, new_session_id, new_trace_id


def test_speaker_interaction_state_vocabulary_is_semantic():
    assert {x.value for x in InteractionState} == {
        "IDLE", "LISTENING", "TRANSCRIBING", "IDENTIFYING",
        "PROCESSING_LOCAL", "PROCESSING_GLOBAL", "USING_TOOL",
        "WAITING_CLARIFICATION", "SPEAKING", "ERROR",
    }


def test_identity_feedback_is_transient_correlated_event():
    event = IdentityFeedbackEvent(
        feedback=IdentityFeedback.IDENTITY_CHANGED,
        source={"id": "nyra-soggiorno", "area": "soggiorno"},
        session_id=new_session_id(),
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )
    assert event.event == "IDENTITY_FEEDBACK"
    assert event.category is EventCategory.IDENTITY
    assert event.source.id == "nyra-soggiorno"
