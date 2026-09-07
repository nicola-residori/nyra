from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


class EnrollmentUnauthorized(RuntimeError):
    pass


class EnrollmentConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentAudioStart:
    audio_stream_id: str
    session_id: str
    request_id: str
    source_id: str
    language: str
    enrollment_session_id: str
    user_id: str
    purpose: str = "ENROLLMENT"
    audio_format: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": "START", "audio_stream_id": self.audio_stream_id,
            "purpose": self.purpose, "session_id": self.session_id,
            "request_id": self.request_id, "source_id": self.source_id,
            "language": self.language, "enrollment_session_id": self.enrollment_session_id,
            "user_id": self.user_id, "audio_format": self.audio_format,
            "sample_rate": self.sample_rate, "channels": self.channels,
        }


class EnrollmentCoordinator:
    """HA owns user authentication; Router owns all enrollment business state."""

    def __init__(self, client, on_update=None, record_output=None,
                 capture_timeout_seconds: float = 35.0):
        self.client = client
        self.on_update = on_update
        self.record_output = record_output
        self._active_by_source: dict[str, dict[str, Any]] = {}
        self._sessions_by_id: dict[str, dict[str, Any]] = {}
        self._capture_by_source: dict[str, str] = {}
        self._capture_error_by_source: dict[str, str | None] = {}
        self._capture_timeout_seconds = capture_timeout_seconds
        self._capture_timeout_handles: dict[str, asyncio.TimerHandle] = {}

    async def async_start(self, authenticated_user_id: str | None, source_id: str,
                          language: str, target_count: int = 6) -> dict[str, Any]:
        if not authenticated_user_id:
            raise EnrollmentUnauthorized("an authenticated Home Assistant user is required")
        session = await self.client.async_start_enrollment(
            profile_user_id=authenticated_user_id, source_id=source_id,
            language=language, target_count=target_count,
        )
        if session.get("profile_user_id") != authenticated_user_id or session.get("source_id") != source_id:
            raise EnrollmentConflict("Router returned a mismatched enrollment binding")
        self._update_session(session)
        self._capture_by_source.setdefault(source_id, "READY")
        self._capture_error_by_source[source_id] = None
        presented = self._present(session)
        await self._notify(presented)
        return presented

    async def async_restore(self, source_ids) -> list[dict[str, Any]]:
        restored = []
        for source_id in dict.fromkeys(source_ids):
            session = await self.client.async_get_active_enrollment(source_id)
            if session is None:
                continue
            self._update_session(session)
            self._capture_by_source.setdefault(source_id, "READY")
            self._capture_error_by_source.setdefault(source_id, None)
            restored.append(session)
        return restored

    def state_for_user(self, authenticated_user_id: str | None) -> list[dict[str, Any]]:
        if not authenticated_user_id:
            return []
        return [
            self._present(session)
            for session in self._sessions_by_id.values()
            if session.get("profile_user_id") == authenticated_user_id
        ]

    async def async_record(self, authenticated_user_id: str | None,
                           session_id: str) -> dict[str, Any]:
        if not authenticated_user_id:
            raise EnrollmentUnauthorized("an authenticated Home Assistant user is required")
        session = self._sessions_by_id.get(session_id)
        if session is None or session.get("profile_user_id") != authenticated_user_id:
            raise EnrollmentUnauthorized("enrollment belongs to a different Home Assistant user")
        if session.get("status") != "ACTIVE":
            raise EnrollmentConflict("enrollment session is not active")
        source_id = session["source_id"]
        if self._capture_by_source.get(source_id) in {"RECORDING", "PROCESSING"}:
            raise EnrollmentConflict("the selected speaker is already recording")
        if self.record_output is None:
            raise EnrollmentConflict("enrollment capture output is unavailable")

        self._capture_by_source[source_id] = "RECORDING"
        self._capture_error_by_source[source_id] = None
        await self._notify(self._present(session))
        try:
            await self.record_output.record_enrollment_sample(source_id)
        except Exception:
            self._capture_by_source[source_id] = "READY"
            self._capture_error_by_source[source_id] = "SPEAKER_UNAVAILABLE"
            await self._notify(self._present(session))
            raise
        self._schedule_capture_timeout(source_id, session_id)
        return self._present(session)

    def audio_metadata(self, metadata):
        if getattr(metadata, "capture_purpose", "IDENTIFICATION") != "ENROLLMENT_CAPTURE":
            return metadata
        session = self._active_by_source.get(metadata.source_id)
        if session is None or session.get("status") != "ACTIVE":
            raise EnrollmentConflict("no active enrollment for the selected speaker")
        if self._capture_by_source.get(metadata.source_id) != "RECORDING":
            raise EnrollmentConflict("no pending enrollment recording for the selected speaker")
        return EnrollmentAudioStart(
            audio_stream_id=metadata.audio_stream_id, session_id=metadata.session_id,
            request_id=metadata.request_id, source_id=metadata.source_id,
            language=session["language"], enrollment_session_id=session["session_id"],
            user_id=session["profile_user_id"], audio_format=metadata.audio_format,
            sample_rate=metadata.sample_rate, channels=metadata.channels,
        )

    async def async_record_result(self, metadata, result: dict[str, Any]) -> dict[str, Any] | None:
        if getattr(metadata, "purpose", None) != "ENROLLMENT":
            return None
        if result.get("user_id") != metadata.user_id:
            raise EnrollmentConflict("Speaker-ID returned a mismatched profile user")
        self._cancel_capture_timeout(metadata.source_id)
        current = self._sessions_by_id.get(metadata.enrollment_session_id)
        if current is not None:
            self._capture_by_source[metadata.source_id] = "PROCESSING"
            await self._notify(self._present(current))
        session = await self.client.async_record_enrollment_attempt(
            metadata.enrollment_session_id,
            {"status": result.get("status"), "sample_id": result.get("sample_id"),
             "reason_code": result.get("reason_code")},
        )
        self._update_session(session)
        result_status = result.get("status")
        if session.get("status") == "COMPLETED":
            capture_state = "COMPLETED"
        elif result_status == "ACCEPTED":
            capture_state = "ACCEPTED"
        elif result_status == "REJECTED":
            capture_state = "REJECTED"
        else:
            capture_state = "FAILED"
        self._capture_by_source[metadata.source_id] = capture_state
        self._capture_error_by_source[metadata.source_id] = result.get("reason_code")
        presented = self._present(session)
        await self._notify(presented)
        return presented

    async def async_terminate(self, authenticated_user_id: str | None, session_id: str,
                              reason: str = "user_cancelled") -> dict[str, Any]:
        if not authenticated_user_id:
            raise EnrollmentUnauthorized("an authenticated Home Assistant user is required")
        active = next((item for item in self._active_by_source.values()
                       if item.get("session_id") == session_id), None)
        if active is None or active.get("profile_user_id") != authenticated_user_id:
            raise EnrollmentUnauthorized("enrollment belongs to a different Home Assistant user")
        session = await self.client.async_terminate_enrollment(session_id, reason)
        self._update_session(session)
        self._cancel_capture_timeout(session["source_id"])
        self._capture_by_source[session["source_id"]] = "TERMINATED"
        presented = self._present(session)
        await self._notify(presented)
        return presented

    def _update_session(self, session: dict[str, Any]) -> None:
        source_id = session["source_id"]
        self._sessions_by_id[session["session_id"]] = session
        if session.get("status") == "ACTIVE":
            self._active_by_source[source_id] = session
        else:
            self._active_by_source.pop(source_id, None)

    def _present(self, session: dict[str, Any]) -> dict[str, Any]:
        source_id = session["source_id"]
        return {
            **session,
            "capture_state": self._capture_by_source.get(source_id, "READY"),
            "capture_error": self._capture_error_by_source.get(source_id),
        }

    async def _notify(self, session):
        if self.on_update is not None:
            result = self.on_update(session)
            if hasattr(result, "__await__"):
                await result

    def _schedule_capture_timeout(self, source_id: str, session_id: str) -> None:
        self._cancel_capture_timeout(source_id)
        loop = asyncio.get_running_loop()

        def expired() -> None:
            self._capture_timeout_handles.pop(source_id, None)
            loop.create_task(self._async_capture_timeout(source_id, session_id))

        self._capture_timeout_handles[source_id] = loop.call_later(
            self._capture_timeout_seconds, expired
        )

    def _cancel_capture_timeout(self, source_id: str) -> None:
        handle = self._capture_timeout_handles.pop(source_id, None)
        if handle is not None:
            handle.cancel()

    async def _async_capture_timeout(self, source_id: str, session_id: str) -> None:
        session = self._sessions_by_id.get(session_id)
        if session is None or session.get("source_id") != source_id:
            return
        if self._capture_by_source.get(source_id) not in {"RECORDING", "PROCESSING"}:
            return
        self._capture_by_source[source_id] = "READY"
        self._capture_error_by_source[source_id] = "CAPTURE_TIMEOUT"
        await self._notify(self._present(session))


_MESSAGES = {
    "it": {
        "COMPLETED": "Ho completato la registrazione della tua voce.",
        "TOO_SHORT": "Il campione è troppo breve. Ripeti la stessa frase.",
        "DEFAULT_REJECTED": "Il campione non è valido. Ripeti la stessa frase.",
        "TERMINATED": "Ho interrotto la registrazione della voce.",
    },
    "en": {
        "COMPLETED": "I have completed your voice enrollment.",
        "TOO_SHORT": "The sample is too short. Repeat the same phrase.",
        "DEFAULT_REJECTED": "The sample is not valid. Repeat the same phrase.",
        "TERMINATED": "I stopped the voice enrollment.",
    },
}


def localized_enrollment_message(language: str, status: str, reason_code: str | None = None) -> str:
    messages = _MESSAGES.get(language.split("-", 1)[0].lower(), _MESSAGES["en"])
    if status == "COMPLETED":
        return messages["COMPLETED"]
    if status == "TERMINATED":
        return messages["TERMINATED"]
    return messages.get(reason_code or "", messages["DEFAULT_REJECTED"])


async def handle_start_enrollment(call, coordinator: EnrollmentCoordinator):
    return await coordinator.async_start(
        authenticated_user_id=getattr(getattr(call, "context", None), "user_id", None),
        source_id=call.data["source_id"], language=call.data.get("language", "it-IT"),
        target_count=call.data.get("sample_count", 6),
    )


async def handle_terminate_enrollment(call, coordinator: EnrollmentCoordinator):
    return await coordinator.async_terminate(
        authenticated_user_id=getattr(getattr(call, "context", None), "user_id", None),
        session_id=call.data["session_id"], reason="user_cancelled",
    )


async def handle_record_enrollment(call, coordinator: EnrollmentCoordinator):
    return await coordinator.async_record(
        authenticated_user_id=getattr(getattr(call, "context", None), "user_id", None),
        session_id=call.data["session_id"],
    )


def register_enrollment_services(hass, coordinator: EnrollmentCoordinator) -> None:
    from homeassistant.core import SupportsResponse

    async def start(call):
        return await handle_start_enrollment(call, coordinator)

    async def terminate(call):
        return await handle_terminate_enrollment(call, coordinator)

    async def record(call):
        return await handle_record_enrollment(call, coordinator)

    hass.services.async_register(
        "nyra", "start_enrollment",
        start,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        "nyra", "record_enrollment_sample",
        record,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        "nyra", "terminate_enrollment",
        terminate,
        supports_response=SupportsResponse.ONLY,
    )


def unregister_enrollment_services(hass) -> None:
    hass.services.async_remove("nyra", "start_enrollment")
    hass.services.async_remove("nyra", "record_enrollment_sample")
    hass.services.async_remove("nyra", "terminate_enrollment")
