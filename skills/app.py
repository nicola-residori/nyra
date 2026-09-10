from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCheckResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
)
from skills.config import SkillsSettings
from skills.job_store import JobStore
from skills.jobs import JobScheduler, UnsupportedJobStop
from skills.modules import (
    RouterHomeAssistantCapabilityClient,
    register_builtin_skills,
)
from skills.registry import SkillRegistry
from skills.service import SkillsService


def _default_service(settings: SkillsSettings) -> SkillsService:
    registry = SkillRegistry()
    capability = (
        RouterHomeAssistantCapabilityClient(
            settings.router_url,
            timeout=settings.router_timeout_seconds,
        )
        if settings.router_url
        else None
    )
    job_store = JobStore(settings.job_db_path)
    scheduler = JobScheduler(
        job_store,
        capability,
        poll_interval_seconds=settings.job_poll_interval_seconds,
    )
    register_builtin_skills(
        registry,
        home_assistant_capability=capability,
        job_scheduler=scheduler,
    )
    return SkillsService(
        registry=registry,
        job_store=job_store,
        scheduler=scheduler,
    )


def create_app(
    settings: SkillsSettings | None = None,
    *,
    service: SkillsService | None = None,
) -> FastAPI:
    settings = settings or SkillsSettings.load()
    service = service or _default_service(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await service.start()
        try:
            yield
        finally:
            await service.shutdown()

    app = FastAPI(title="Nyra Skills", lifespan=lifespan)
    app.state.settings = settings
    app.state.skills_service = service

    @app.get("/health")
    def health():
        return {"service": "nyra-skills", "status": "ok"}

    @app.get("/ready")
    def ready():
        if service.is_ready():
            return {"service": "nyra-skills", "status": "ready"}
        return JSONResponse(
            {"service": "nyra-skills", "status": "not_ready"},
            status_code=503,
        )

    @app.post("/v1/skills/check", response_model=SkillCheckResponse)
    async def check(request: SkillCheckRequest) -> SkillCheckResponse:
        return await service.check(request)

    @app.post("/v1/skills/execute", response_model=SkillExecuteResponse)
    async def execute(request: SkillExecuteRequest) -> SkillExecuteResponse:
        return await service.execute(request)

    @app.get("/v1/jobs")
    def list_jobs():
        return [job.model_dump(mode="json") for job in service.list_jobs()]

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str):
        job = service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.model_dump(mode="json")

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        job = await service.cancel_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.model_dump(mode="json")

    @app.post("/v1/jobs/{job_id}/stop")
    async def stop_job(job_id: str):
        try:
            job = await service.stop_job(job_id)
        except UnsupportedJobStop as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.model_dump(mode="json")

    return app


app = create_app()
