from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class SpeakerIdentityOutcome(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    NOT_RECOGNIZED = "NOT_RECOGNIZED"
    FAILED = "FAILED"


class InvalidSpeakerIdentityResponse(ValueError):
    pass


@dataclass(frozen=True)
class SpeakerIdentityRequest:
    audio_stream_id: str
    session_id: str | None
    request_id: str | None
    source_id: str | None
    trace_id: str
    span_id: str


@dataclass(frozen=True)
class SpeakerIdentityResult:
    outcome: SpeakerIdentityOutcome
    identified_user_id: str | None
    best_score: float | None
    diagnostic_id: str | None
    reason_code: str | None


@dataclass(frozen=True)
class DiagnosticCandidate:
    user_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class SpeakerIdentityDiagnostic:
    diagnostic_id: str
    outcome: SpeakerIdentityOutcome
    identified_user_id: str | None
    best_score: float | None
    reason_code: str | None
    candidates: tuple[DiagnosticCandidate, ...]


class JsonTransport(Protocol):
    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class SpeakerIdentityClient:
    def __init__(self, transport: JsonTransport):
        self.transport = transport

    async def identify(self, request: SpeakerIdentityRequest) -> SpeakerIdentityResult:
        payload = {
            "audio_stream_id": request.audio_stream_id,
            "session_id": request.session_id,
            "request_id": request.request_id,
            "source_id": request.source_id,
            "trace_id": request.trace_id,
            "span_id": request.span_id,
        }
        raw = await self.transport.post_json("/v1/identify", payload)
        return _parse_realtime(raw)

    async def get_diagnostic(self, diagnostic_id: str) -> SpeakerIdentityDiagnostic:
        raw = await self.transport.post_json(f"/v1/diagnostics/{diagnostic_id}", {})
        outcome = _parse_outcome(raw.get("outcome"))
        identified_user_id = raw.get("identified_user_id")
        _validate_identity(outcome, identified_user_id)
        try:
            candidates = tuple(
                DiagnosticCandidate(
                    user_id=str(item["user_id"]),
                    score=float(item["score"]),
                    rank=int(item["rank"]),
                )
                for item in raw.get("candidate_scores", [])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSpeakerIdentityResponse("invalid candidate scores") from exc
        return SpeakerIdentityDiagnostic(
            diagnostic_id=str(raw.get("diagnostic_id") or diagnostic_id),
            outcome=outcome,
            identified_user_id=identified_user_id,
            best_score=_optional_float(raw.get("best_score")),
            reason_code=_optional_str(raw.get("reason_code")),
            candidates=candidates,
        )


def _parse_realtime(raw: dict[str, Any]) -> SpeakerIdentityResult:
    outcome = _parse_outcome(raw.get("outcome"))
    identified_user_id = raw.get("identified_user_id")
    _validate_identity(outcome, identified_user_id)
    return SpeakerIdentityResult(
        outcome=outcome,
        identified_user_id=identified_user_id,
        best_score=_optional_float(raw.get("best_score")),
        diagnostic_id=_optional_str(raw.get("diagnostic_id")),
        reason_code=_optional_str(raw.get("reason_code")),
    )


def _parse_outcome(value: Any) -> SpeakerIdentityOutcome:
    try:
        return SpeakerIdentityOutcome(value)
    except (ValueError, TypeError) as exc:
        raise InvalidSpeakerIdentityResponse(f"invalid outcome: {value!r}") from exc


def _validate_identity(outcome: SpeakerIdentityOutcome, user_id: Any) -> None:
    if user_id == "guest":
        raise InvalidSpeakerIdentityResponse("Speaker-ID must never return guest")
    if outcome is SpeakerIdentityOutcome.IDENTIFIED:
        if not isinstance(user_id, str) or not user_id:
            raise InvalidSpeakerIdentityResponse("IDENTIFIED requires identified_user_id")
    elif user_id is not None:
        raise InvalidSpeakerIdentityResponse(f"{outcome.value} cannot expose identity")


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSpeakerIdentityResponse("invalid numeric field") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidSpeakerIdentityResponse("invalid string field")
    return value
