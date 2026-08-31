from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.protocol.events import (
    IdentityFeedback,
    IdentityFeedbackEvent,
    InteractionState,
    InteractionStateChanged,
    SessionClosedEvent,
)


class SpeakerOutputPort(Protocol):
    async def set_idle(self, source_id: str) -> None: ...
    async def pulse_white_fast(self, source_id: str) -> None: ...
    async def comet_warm_white(self, source_id: str) -> None: ...
    async def blink_identity(self, source_id: str, feedback: IdentityFeedback, count: int) -> None: ...
    async def comet_turquoise(self, source_id: str) -> None: ...
    async def comet_rainbow(self, source_id: str) -> None: ...
    async def comet_yellow(self, source_id: str) -> None: ...
    async def speaking_purple(self, source_id: str) -> None: ...
    async def error_red(self, source_id: str) -> None: ...
    async def close_feedback(self, source_id: str) -> None: ...


@dataclass
class _SpeakerState:
    processing_state: InteractionState | None = None


class SpeakerStateMachine:
    def __init__(self, output: SpeakerOutputPort):
        self.output = output
        self._states: dict[str, _SpeakerState] = {}

    def _source_id(self, event) -> str | None:
        return event.source.id if getattr(event, "source", None) is not None else None

    async def handle_state(self, event: InteractionStateChanged) -> None:
        source_id = self._source_id(event)
        if not source_id:
            return
        state = self._states.setdefault(source_id, _SpeakerState())
        current = event.state

        if current is InteractionState.IDLE:
            state.processing_state = None
            await self.output.set_idle(source_id)
        elif current in {
            InteractionState.LISTENING,
            InteractionState.TRANSCRIBING,
            InteractionState.WAITING_CLARIFICATION,
        }:
            await self.output.pulse_white_fast(source_id)
        elif current is InteractionState.IDENTIFYING:
            await self.output.comet_warm_white(source_id)
        elif current is InteractionState.PROCESSING_LOCAL:
            state.processing_state = current
            await self.output.comet_turquoise(source_id)
        elif current is InteractionState.PROCESSING_GLOBAL:
            state.processing_state = current
            await self.output.comet_rainbow(source_id)
        elif current is InteractionState.USING_TOOL:
            await self.output.comet_yellow(source_id)
        elif current is InteractionState.SPEAKING:
            await self.output.speaking_purple(source_id)
        elif current is InteractionState.ERROR:
            await self.output.error_red(source_id)

    async def restore_processing(self, source_id: str) -> None:
        state = self._states.get(source_id)
        if state is None:
            return
        if state.processing_state is InteractionState.PROCESSING_LOCAL:
            await self.output.comet_turquoise(source_id)
        elif state.processing_state is InteractionState.PROCESSING_GLOBAL:
            await self.output.comet_rainbow(source_id)

    async def handle_identity(self, event: IdentityFeedbackEvent) -> None:
        source_id = self._source_id(event)
        if source_id:
            await self.output.blink_identity(source_id, event.feedback, 2)

    async def handle_session_closed(self, event: SessionClosedEvent) -> None:
        source_id = self._source_id(event)
        if source_id:
            await self.output.close_feedback(source_id)
            await self.output.set_idle(source_id)
            self._states.pop(source_id, None)
