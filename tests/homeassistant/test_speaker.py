import asyncio

import pytest

from homeassistant.custom_components.nyra.speaker import SpeakerStateMachine
from shared.protocol.events import (
    IdentityFeedback,
    IdentityFeedbackEvent,
    InteractionState,
    InteractionStateChanged,
    SessionClosedEvent,
)
from shared.protocol.requests import CloseReason


class Output:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def call(*args):
            self.calls.append((name, *args))

        return call


@pytest.mark.asyncio
async def test_visual_contract_and_tool_restore():
    out = Output()
    sm = SpeakerStateMachine(out)
    source = {"id": "speaker-a"}

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.LISTENING,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.TRANSCRIBING,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_GLOBAL,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.USING_TOOL,
            source=source,
        )
    )
    await sm.restore_processing("speaker-a")
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.WAITING_CLARIFICATION,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.SPEAKING,
            source=source,
        )
    )

    assert [x[0] for x in out.calls] == [
        "pulse_white_fast",
        "pulse_white_fast",
        "comet_rainbow",
        "comet_yellow",
        "comet_rainbow",
        "pulse_white_fast",
        "speaking_purple",
    ]


@pytest.mark.asyncio
async def test_identity_is_exactly_two_blinks_and_session_close_goes_idle():
    out = Output()
    sm = SpeakerStateMachine(out)
    source = {"id": "speaker-a"}

    await sm.handle_identity(
        IdentityFeedbackEvent(
            feedback=IdentityFeedback.RECOGNIZED,
            source=source,
        )
    )
    await sm.handle_session_closed(
        SessionClosedEvent(
            close_reason=CloseReason.DIRECT_COMMAND,
            source=source,
        )
    )

    assert out.calls[0] == (
        "blink_identity",
        "speaker-a",
        IdentityFeedback.RECOGNIZED,
        2,
    )
    assert out.calls[-2:] == [
        ("close_feedback", "speaker-a"),
        ("set_idle", "speaker-a"),
    ]


@pytest.mark.asyncio
async def test_processing_state_waits_for_identity_feedback_then_restores_latest():
    feedback_started = asyncio.Event()
    release_feedback = asyncio.Event()

    async def controlled_sleep(_: float) -> None:
        feedback_started.set()
        await release_feedback.wait()

    out = Output()
    sm = SpeakerStateMachine(
        out,
        identity_feedback_seconds=0.65,
        sleep=controlled_sleep,
    )
    source = {"id": "nyra-mansarda"}

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_LOCAL,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.IDENTIFYING,
            source=source,
        )
    )
    await sm.handle_identity(
        IdentityFeedbackEvent(
            feedback=IdentityFeedback.NOT_RECOGNIZED,
            source=source,
        )
    )

    await feedback_started.wait()

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_LOCAL,
            source=source,
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_GLOBAL,
            source=source,
        )
    )

    assert out.calls[-1] == (
        "blink_identity",
        "nyra-mansarda",
        IdentityFeedback.NOT_RECOGNIZED,
        2,
    )

    release_feedback.set()
    await asyncio.sleep(0)

    assert out.calls[-1] == ("comet_rainbow", "nyra-mansarda")


@pytest.mark.asyncio
async def test_concurrent_speakers_never_cross_target():
    out = Output()
    sm = SpeakerStateMachine(out)

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_LOCAL,
            source={"id": "a"},
        )
    )
    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_GLOBAL,
            source={"id": "b"},
        )
    )

    assert out.calls == [
        ("comet_turquoise", "a"),
        ("comet_rainbow", "b"),
    ]


@pytest.mark.asyncio
async def test_local_playback_does_not_restore_stale_processing_after_playback_ends():
    out = Output()
    sm = SpeakerStateMachine(out)
    source = {"id": "speaker-a"}

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_GLOBAL,
            source=source,
        )
    )
    await sm.begin_speaking("speaker-a")

    await sm.handle_state(
        InteractionStateChanged(
            state=InteractionState.PROCESSING_LOCAL,
            source=source,
        )
    )
    calls_before_end = list(out.calls)

    await sm.end_speaking("speaker-a")

    assert out.calls == calls_before_end
