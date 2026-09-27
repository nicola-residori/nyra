from __future__ import annotations
from fastapi import FastAPI,HTTPException
from shared.protocol.llm import LlmPurpose,LlmRequest
from llm.config import LlmSettings
from llm.provider_service import ProviderService
from llm.observability import LlmDiagnostics
from llm.providers.litellm_adapter import LiteLlmAdapter
from llm.service import LlmService

def build_service(settings:LlmSettings|None=None,diagnostics:LlmDiagnostics|None=None)->LlmService:
    settings=settings or LlmSettings.load()
    return LlmService(ProviderService(
            LiteLlmAdapter(),settings.primary,settings.fallback,
            purpose_targets={
                LlmPurpose.SEMANTIC.value: settings.semantic,
                LlmPurpose.REASONING.value: settings.reasoning,
            },
            diagnostics=diagnostics,
        ))

def create_app(*,service=None,settings:LlmSettings|None=None)->FastAPI:
    app=FastAPI(title="Nyra LLM")
    app.state.llm_diagnostics=LlmDiagnostics()
    app.state.service=service if service is not None else build_service(settings,app.state.llm_diagnostics)

    @app.get("/health")
    async def health():
        return {"status":"ok"}

    @app.get("/ready")
    async def ready():
        return {"status":"ready"}

    @app.post("/v1/llm/semantic")
    async def semantic(request:LlmRequest):
        if request.purpose is not LlmPurpose.SEMANTIC:
            raise HTTPException(status_code=422,detail="SEMANTIC purpose required")
        return await app.state.service.semantic(request)

    @app.post("/v1/llm/reason")
    async def reason(request:LlmRequest):
        if request.purpose is not LlmPurpose.REASONING:
            raise HTTPException(status_code=422,detail="REASONING purpose required")
        return await app.state.service.reason(request)

    return app
