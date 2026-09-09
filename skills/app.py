from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCheckResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
)
from skills.config import SkillsSettings
from skills.modules import register_builtin_skills
from skills.registry import SkillRegistry
from skills.service import SkillsService


def _default_service() -> SkillsService:
    registry = SkillRegistry()
    register_builtin_skills(registry)
    return SkillsService(registry=registry)


def create_app(
    settings: SkillsSettings | None = None,
    *,
    service: SkillsService | None = None,
) -> FastAPI:
    settings = settings or SkillsSettings.load()
    service = service or _default_service()

    app = FastAPI(title="Nyra Skills")
    app.state.settings = settings
    app.state.skills_service = service

    @app.get("/health")
    def health():
        return {
            "service": "nyra-skills",
            "status": "ok",
        }

    @app.get("/ready")
    def ready():
        if service.is_ready():
            return {
                "service": "nyra-skills",
                "status": "ready",
            }
        return JSONResponse(
            {
                "service": "nyra-skills",
                "status": "not_ready",
            },
            status_code=503,
        )

    @app.post(
        "/v1/skills/check",
        response_model=SkillCheckResponse,
    )
    async def check(request: SkillCheckRequest) -> SkillCheckResponse:
        return await service.check(request)

    @app.post(
        "/v1/skills/execute",
        response_model=SkillExecuteResponse,
    )
    async def execute(request: SkillExecuteRequest) -> SkillExecuteResponse:
        return await service.execute(request)

    return app


app = create_app()
