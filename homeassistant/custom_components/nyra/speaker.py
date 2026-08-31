from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from shared.protocol.events import (
    IdentityFeedback,
    IdentityFeedbackEvent,
    InteractionState,
    InteractionStateChanged,
    SessionClosedEvent,
)

IDENTITY_FEEDBACK_SECONDS = 0.65
Sleep = Callable[[float], Awaitable[None]]


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
    pending_state: InteractionState | None = None
    identity_task: asyncio.Task | None = None


class SpeakerStateMachine:
    def __init__(
        self,
        output: SpeakerOutputPort,
        *,
        identity_feedback_seconds: float = IDENTITY_FEEDBACK_SECONDS,
        sleep: Sleep = asyncio.sleep,
    ):
        self.output = output
        self._states: dict[str, _SpeakerState] = {}
        self._identity_feedback_seconds = identity_feedback_seconds
        self._sleep = sleep

    def _source_id(self, event) -> str | None:
        return event.source.id if getattr(event, "source", None) is not None else None

    async def _render_state(
        self,
        source_id: str,
        state: _SpeakerState,
        current: InteractionState,
    ) -> None:
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
            await self.output.comet_turquoise(source_id)
        elif current is InteractionState.PROCESSING_GLOBAL:
            await self.output.comet_rainbow(source_id)
        elif current is InteractionState.USING_TOOL:
            await self.output.comet_yellow(source_id)
        elif current is InteractionState.SPEAKING:
            await self.output.speaking_purple(source_id)
        elif current is InteractionState.ERROR:
            await self.output.error_red(source_id)

    async def handle_state(self, event: InteractionStateChanged) -> None:
        source_id = self._source_id(event)
        if not source_id:
            return
        state = self._states.setdefault(source_id, _SpeakerState())
        current = event.state
        if current in {InteractionState.PROCESSING_LOCAL, InteractionState.PROCESSING_GLOBAL}:
            state.processing_state = current
        if state.identity_task is not None and not state.identity_task.done():
            state.pending_state = current
            return
        await self._render_state(source_id, state, current)

    async def restore_processing(self, source_id: str) -> None:
        state = self._states.get(source_id)
        if state is None or state.processing_state is None:
            return
        if state.identity_task is not None and not state.identity_task.done():
            state.pending_state = state.processing_state
            return
        await self._render_state(source_id, state, state.processing_state)

    async def _finish_identity_feedback(self, source_id: str, state: _SpeakerState) -> None:
        try:
            await self._sleep(self._identity_feedback_seconds)
        except asyncio.CancelledError:
            return
        state.identity_task = None
        pending = state.pending_state
        state.pending_state = None
        if pending is not None:
            await self._render_state(source_id, state, pending)
        else:
            await self.restore_processing(source_id)

    async def handle_identity(self, event: IdentityFeedbackEvent) -> None:
        source_id = self._source_id(event)
        if not source_id:
            return
        state = self._states.setdefault(source_id, _SpeakerState())
        if state.identity_task is not None and not state.identity_task.done():
            state.identity_task.cancel()
        state.pending_state = None
        await self.output.blink_identity(source_id, event.feedback, 2)
        state.identity_task = asyncio.create_task(
            self._finish_identity_feedback(source_id, state)
        )

    async def handle_session_closed(self, event: SessionClosedEvent) -> None:
        source_id = self._source_id(event)
        if source_id:
            state = self._states.get(source_id)
            if state is not None and state.identity_task is not None and not state.identity_task.done():
                state.identity_task.cancel()
            await self.output.close_feedback(source_id)
            await self.output.set_idle(source_id)
            self._states.pop(source_id, None)
