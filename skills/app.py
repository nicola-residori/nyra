from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from skills.config import SkillsSettings
from skills.service import SkillsService


def create_app(
    settings: SkillsSettings | None = None,
    *,
    service: SkillsService | None = None,
) -> FastAPI:
    settings = settings or SkillsSettings.load()
    service = service or SkillsService()

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

    return app


app = create_app()
