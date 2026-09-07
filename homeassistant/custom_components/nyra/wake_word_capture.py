from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .enrollment import EnrollmentConflict, EnrollmentUnauthorized


@dataclass(frozen=True)
class WakeWordAudioStart:
    audio_stream_id: str
    session_id: str
    request_id: str
    source_id: str
    language: str
    wake_word_session_id: str
    user_id: str
    wake_word_text: str
    purpose: str = "WAKE_WORD_CAPTURE"
    audio_format: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": "START", "audio_stream_id": self.audio_stream_id,
            "purpose": self.purpose, "session_id": self.session_id,
            "request_id": self.request_id, "source_id": self.source_id,
            "language": self.language, "wake_word_session_id": self.wake_word_session_id,
            "user_id": self.user_id, "wake_word_text": self.wake_word_text,
            "audio_format": self.audio_format, "sample_rate": self.sample_rate,
            "channels": self.channels,
        }


class WakeWordCaptureCoordinator:
    def __init__(self, client, on_update=None, record_output=None,
                 capture_timeout_seconds: float = 35.0):
        self.client = client
        self.on_update = on_update
        self.record_output = record_output
        self._sessions_by_id: dict[str, dict[str, Any]] = {}
        self._active_by_source: dict[str, dict[str, Any]] = {}
        self._capture_state: dict[str, str] = {}
        self._capture_timeout_seconds = capture_timeout_seconds
        self._timeout_handles: dict[str, asyncio.TimerHandle] = {}

    async def async_capture(self, authenticated_user_id: str | None, source_id: str,
                            language: str, wake_word_text: str) -> dict[str, Any]:
        if not authenticated_user_id:
            raise EnrollmentUnauthorized("an authenticated Home Assistant user is required")
        wake_word_text = " ".join(wake_word_text.strip().split())
        if not wake_word_text:
            raise ValueError("wake_word_text is required")
        if source_id in self._active_by_source:
            raise EnrollmentConflict("the selected speaker is already recording")
        session = await self.client.async_start_wake_word_capture(
            user_id=authenticated_user_id, source_id=source_id,
            language=language, wake_word_text=wake_word_text,
        )
        if session.get("user_id") != authenticated_user_id or session.get("source_id") != source_id:
            raise EnrollmentConflict("Router returned a mismatched wake-word binding")
        self._update(session)
        self._capture_state[source_id] = "RECORDING"
        await self._notify(self._present(session))
        try:
            await self.record_output.record_wake_word_sample(source_id)
        except Exception:
            await self._complete_failed(session, "SPEAKER_UNAVAILABLE")
            raise
        self._schedule_timeout(source_id, session["session_id"])
        return self._present(session)

    async def async_restore(self, source_ids) -> list[dict[str, Any]]:
        restored = []
        for source_id in dict.fromkeys(source_ids):
            session = await self.client.async_get_active_wake_word_capture(source_id)
            if session is None:
                continue
            self._update(session)
            self._capture_state[source_id] = "READY"
            restored.append(session)
        return restored

    def state_for_user(self, user_id: str | None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        return [self._present(item) for item in self._sessions_by_id.values()
                if item.get("user_id") == user_id]

    def audio_metadata(self, metadata):
        if getattr(metadata, "capture_purpose", None) != "WAKE_WORD_CAPTURE":
            return metadata
        session = self._active_by_source.get(metadata.source_id)
        if session is None or self._capture_state.get(metadata.source_id) != "RECORDING":
            raise EnrollmentConflict("no active wake-word capture for the selected speaker")
        return WakeWordAudioStart(
            audio_stream_id=metadata.audio_stream_id, session_id=metadata.session_id,
            request_id=metadata.request_id, source_id=metadata.source_id,
            language=session["language"], wake_word_session_id=session["session_id"],
            user_id=session["user_id"], wake_word_text=session["wake_word_text"],
            audio_format=metadata.audio_format, sample_rate=metadata.sample_rate,
            channels=metadata.channels,
        )

    async def async_record_result(self, metadata, result: dict[str, Any]):
        if getattr(metadata, "purpose", None) != "WAKE_WORD_CAPTURE":
            return None
        if result.get("capture_id") != metadata.wake_word_session_id:
            raise EnrollmentConflict("Speaker-ID returned a mismatched wake-word capture")
        self._cancel_timeout(metadata.source_id)
        session = await self.client.async_complete_wake_word_capture(
            metadata.wake_word_session_id,
            {"status": result.get("status"), "sample_id": result.get("sample_id"),
             "reason_code": result.get("reason_code")},
        )
        self._update(session)
        self._capture_state[metadata.source_id] = session["status"]
        presented = self._present(session)
        await self._notify(presented)
        return presented

    def _update(self, session):
        self._sessions_by_id[session["session_id"]] = session
        if session.get("status") == "ACTIVE":
            self._active_by_source[session["source_id"]] = session
        else:
            self._active_by_source.pop(session["source_id"], None)

    def _present(self, session):
        return {**session, "capture_state": self._capture_state.get(session["source_id"], "READY")}

    async def _notify(self, session):
        if self.on_update is not None:
            result = self.on_update(session)
            if hasattr(result, "__await__"):
                await result

    async def _complete_failed(self, session, reason_code):
        completed = await self.client.async_complete_wake_word_capture(
            session["session_id"],
            {"status": "FAILED", "sample_id": None, "reason_code": reason_code},
        )
        self._update(completed)
        self._capture_state[session["source_id"]] = "FAILED"
        await self._notify(self._present(completed))

    def _schedule_timeout(self, source_id, session_id):
        self._cancel_timeout(source_id)
        loop = asyncio.get_running_loop()
        self._timeout_handles[source_id] = loop.call_later(
            self._capture_timeout_seconds,
            lambda: loop.create_task(self._timeout(source_id, session_id)),
        )

    def _cancel_timeout(self, source_id):
        handle = self._timeout_handles.pop(source_id, None)
        if handle is not None:
            handle.cancel()

    async def _timeout(self, source_id, session_id):
        self._timeout_handles.pop(source_id, None)
        session = self._sessions_by_id.get(session_id)
        if session is not None and session.get("status") == "ACTIVE":
            await self._complete_failed(session, "CAPTURE_TIMEOUT")
