from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from router.api.requests import _authorized
from router.enrollment import EnrollmentConflict, EnrollmentNotFound


router = APIRouter(prefix="/v1/enrollments")


class StartEnrollment(BaseModel):
    profile_user_id: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=1024)
    language: str = Field(min_length=2, max_length=35)
    target_count: int = Field(default=6, ge=1, le=24)


class EnrollmentAttempt(BaseModel):
    status: str
    sample_id: str | None = Field(default=None, min_length=1, max_length=1024)
    reason_code: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_attempt(self):
        if self.status not in {"ACCEPTED", "REJECTED", "FAILED"}:
            raise ValueError("invalid attempt status")
        if self.status == "ACCEPTED" and not self.sample_id:
            raise ValueError("accepted attempt requires sample_id")
        return self


class TerminateEnrollment(BaseModel):
    reason: str = Field(min_length=1, max_length=1024)


def require_auth(request: Request) -> None:
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")


def call(operation):
    try:
        return enrollment_payload(operation())
    except EnrollmentNotFound as exc:
        raise HTTPException(status_code=404, detail="enrollment session not found") from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def enrollment_payload(session):
    phrase = session.current_phrase
    return {
        "session_id": session.session_id,
        "profile_user_id": session.profile_user_id,
        "source_id": session.source_id,
        "language": session.language,
        "target_count": session.target_count,
        "accepted_count": session.accepted_count,
        "accepted_sample_ids": list(session.accepted_sample_ids),
        "phrases": [
            {"text": item.text, "language": item.language, "length_class": item.length_class.value}
            for item in session.phrases
        ],
        "current_phrase": None if phrase is None else {
            "text": phrase.text, "language": phrase.language,
            "length_class": phrase.length_class.value,
        },
        "status": session.status.value,
        "termination_reason": session.termination_reason,
        "last_reason_code": session.last_reason_code,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def start(payload: StartEnrollment, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.enrollments.start(
        payload.profile_user_id, payload.source_id, payload.language, payload.target_count
    ))


@router.get("/{session_id}")
def get(session_id: str, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.enrollments.get(session_id))


@router.get("/active/{source_id}")
def get_active(source_id: str, request: Request):
    require_auth(request)
    session = request.app.state.enrollments.store.get_active_for_source(source_id)
    if session is None:
        raise HTTPException(status_code=404, detail="active enrollment not found")
    return enrollment_payload(session)


@router.post("/{session_id}/attempts")
def attempt(session_id: str, payload: EnrollmentAttempt, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.enrollments.record_attempt(
        session_id, payload.status, sample_id=payload.sample_id, reason_code=payload.reason_code
    ))


@router.post("/{session_id}/terminate")
def terminate(session_id: str, payload: TerminateEnrollment, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.enrollments.terminate(session_id, payload.reason))
