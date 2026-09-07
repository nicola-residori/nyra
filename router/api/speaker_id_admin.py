from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from router.api.enrollments import require_auth
from router.speaker_id_admin import SpeakerIdAdminUnavailable


router = APIRouter(prefix="/v1/admin/speaker-identity")


class Selection(BaseModel):
    sample_ids: list[str]


async def json_call(request, method, path, *, params=None, payload=None):
    require_auth(request)
    try:
        return await request.app.state.speaker_id_admin.json(
            method, path, params=params, payload=payload
        )
    except SpeakerIdAdminUnavailable as exc:
        raise HTTPException(status_code=503, detail="Speaker-ID is unavailable") from exc


async def binary_call(request, method, path, *, payload=None):
    require_auth(request)
    try:
        content, content_type, disposition = await request.app.state.speaker_id_admin.binary(
            method, path, payload=payload
        )
    except SpeakerIdAdminUnavailable as exc:
        raise HTTPException(status_code=503, detail="Speaker-ID is unavailable") from exc
    headers = {"Content-Disposition": disposition} if disposition else None
    return Response(content, media_type=content_type, headers=headers)


@router.get("/profiles")
async def profiles(request: Request):
    return await json_call(request, "GET", "/v1/admin/profiles")


@router.get("/profiles/{user_id}/samples/{sample_id}/audio")
async def profile_audio(user_id: str, sample_id: str, request: Request):
    return await binary_call(
        request, "GET", f"/v1/admin/profiles/{user_id}/samples/{sample_id}/audio"
    )


@router.delete("/profiles/{user_id}/samples")
async def delete_profile_samples(user_id: str, selection: Selection, request: Request):
    return await json_call(
        request, "DELETE", f"/v1/admin/profiles/{user_id}/samples",
        payload=selection.model_dump(),
    )


@router.delete("/profiles/{user_id}")
async def delete_profile(user_id: str, request: Request):
    return await json_call(request, "DELETE", f"/v1/admin/profiles/{user_id}")


@router.get("/diagnostics")
async def diagnostics(request: Request, source_id: str | None = None,
                      outcome: str | None = None, user_id: str | None = None,
                      limit: int = 100):
    params = {key: value for key, value in {
        "source_id": source_id, "outcome": outcome, "user_id": user_id,
        "limit": limit,
    }.items() if value is not None}
    return await json_call(request, "GET", "/v1/admin/diagnostics", params=params)


@router.get("/diagnostics/{diagnostic_id}/audio")
async def diagnostic_audio(diagnostic_id: str, request: Request):
    return await binary_call(
        request, "GET", f"/v1/admin/diagnostics/{diagnostic_id}/audio"
    )


@router.get("/diagnostics/{diagnostic_id}")
async def diagnostic_detail(diagnostic_id: str, request: Request):
    return await json_call(request, "GET", f"/v1/admin/diagnostics/{diagnostic_id}")


@router.get("/wake-words")
async def wake_words(request: Request, wake_word_text: str | None = None,
                     user_id: str | None = None, source_id: str | None = None):
    params = {key: value for key, value in {
        "wake_word_text": wake_word_text, "user_id": user_id,
        "source_id": source_id,
    }.items() if value is not None}
    return await json_call(request, "GET", "/v1/admin/wake-words", params=params)


@router.get("/wake-words/samples/{sample_id}/audio")
async def wake_word_audio(sample_id: str, request: Request):
    return await binary_call(
        request, "GET", f"/v1/admin/wake-words/samples/{sample_id}/audio"
    )


@router.delete("/wake-words/samples")
async def delete_wake_word_samples(selection: Selection, request: Request):
    return await json_call(
        request, "DELETE", "/v1/admin/wake-words/samples",
        payload=selection.model_dump(),
    )


@router.post("/wake-words/export")
async def export_wake_word_samples(selection: Selection, request: Request):
    return await binary_call(
        request, "POST", "/v1/admin/wake-words/export",
        payload=selection.model_dump(),
    )
