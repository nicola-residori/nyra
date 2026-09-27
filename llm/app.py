from __future__ import annotations
from fastapi import FastAPI,HTTPException
from time import monotonic
from shared.logging.client import NyraLogger
from shared.protocol.llm import LlmPurpose,LlmRequest
from llm.config import LlmSettings
from llm.provider_service import ProviderService
from llm.observability import LlmDiagnostics
from llm.providers.litellm_adapter import LiteLlmAdapter
from llm.service import LlmService

def build_service(settings:LlmSettings|None=None,diagnostics:LlmDiagnostics|None=None)->LlmService:
    if settings is None and service is None:
        settings=LlmSettings.load()
    return LlmService(ProviderService(
            LiteLlmAdapter(api_keys=settings.api_keys),settings.primary,settings.fallback,
            purpose_targets={
                LlmPurpose.SEMANTIC.value: settings.semantic,
                LlmPurpose.REASONING.value: settings.reasoning,
            },
            diagnostics=diagnostics,
        ))

def create_app(*,service=None,settings:LlmSettings|None=None,event_sink=None)->FastAPI:
    if settings is None and service is None:
        settings=LlmSettings.load()
    if event_sink is None and settings is not None and settings.router_url: event_sink=NyraLogger(settings.router_url,"LLM",{},spool_path="/var/lib/nyra-llm/log-spool.jsonl")
    app=FastAPI(title="Nyra LLM")
    app.state.llm_diagnostics=LlmDiagnostics(sink=event_sink)
    app.state.service=service if service is not None else build_service(settings,app.state.llm_diagnostics)
    async def observed(purpose,request,call):
        started=monotonic();op=request.context.operational
        try: result=await call(request)
        except Exception:
            app.state.llm_diagnostics.trace(purpose=purpose,outcome="ERROR",trace_id=op.get("trace_id"),request_id=op.get("request_id"),origin_request_id=op.get("origin_request_id"),latency_ms=(monotonic()-started)*1000,fault=True);raise
        app.state.llm_diagnostics.trace(purpose=purpose,outcome="SUCCESS",trace_id=op.get("trace_id"),request_id=op.get("request_id"),origin_request_id=op.get("origin_request_id"),latency_ms=(monotonic()-started)*1000);return result

    @app.get("/health")
    async def health():
        return {"status":"ok"}

    @app.get("/ready")
    async def ready():
        return {"status":"ready"}

    @app.get("/v1/llm/diagnostics")
    async def diagnostics():
        return {"items": app.state.llm_diagnostics.items()}

    @app.post("/v1/llm/semantic")
    async def semantic(request:LlmRequest):
        if request.purpose is not LlmPurpose.SEMANTIC:
            raise HTTPException(status_code=422,detail="SEMANTIC purpose required")
        return await observed("SEMANTIC",request,app.state.service.semantic)

    @app.post("/v1/llm/reason")
    async def reason(request:LlmRequest):
        if request.purpose is not LlmPurpose.REASONING:
            raise HTTPException(status_code=422,detail="REASONING purpose required")
        return await observed("REASONING",request,app.state.service.reason)

    return app
