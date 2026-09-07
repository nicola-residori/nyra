from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from router.api.enrollments import require_auth
from router.wake_word_capture import WakeWordCaptureConflict, WakeWordCaptureNotFound


router = APIRouter(prefix="/v1/wake-word-captures")


class StartCapture(BaseModel):
    user_id: str = Field(min_length=1, max_length=1024)
    source_id: str = Field(min_length=1, max_length=1024)
    language: str = Field(min_length=2, max_length=35)
    wake_word_text: str = Field(min_length=1, max_length=120)


class CaptureResult(BaseModel):
    status: str
    sample_id: str | None = Field(default=None, min_length=1, max_length=1024)
    reason_code: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status not in {"ACCEPTED", "REJECTED", "FAILED"}:
            raise ValueError("invalid capture status")
        if self.status == "ACCEPTED" and not self.sample_id:
            raise ValueError("accepted capture requires sample_id")
        return self


def payload(session):
    return {
        "session_id": session.session_id, "user_id": session.user_id,
        "source_id": session.source_id, "language": session.language,
        "wake_word_text": session.wake_word_text, "status": session.status.value,
        "sample_id": session.sample_id, "reason_code": session.reason_code,
    }


def call(operation):
    try:
        return payload(operation())
    except WakeWordCaptureNotFound as exc:
        raise HTTPException(status_code=404, detail="wake-word capture not found") from exc
    except WakeWordCaptureConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def start_capture(body: StartCapture, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.wake_word_captures.start(
        body.user_id, body.source_id, body.language, body.wake_word_text
    ))


@router.get("/sample-count")
async def sample_count(wake_word_text: str, request: Request):
    require_auth(request)
    normalized = " ".join(wake_word_text.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail="wake_word_text is required")
    try:
        count = await request.app.state.wake_word_dataset.count(normalized)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="wake-word dataset is unavailable") from exc
    return {"wake_word_text": normalized, "sample_count": count}


@router.get("/active/{source_id}")
def active_capture(source_id: str, request: Request):
    require_auth(request)
    session = request.app.state.wake_word_capture_store.get_active_for_source(source_id)
    if session is None:
        raise HTTPException(status_code=404, detail="active wake-word capture not found")
    return payload(session)


@router.post("/{session_id}/result")
def complete_capture(session_id: str, body: CaptureResult, request: Request):
    require_auth(request)
    return call(lambda: request.app.state.wake_word_captures.complete(
        session_id, body.status, sample_id=body.sample_id, reason_code=body.reason_code
    ))
