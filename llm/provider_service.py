from __future__ import annotations
from dataclasses import replace
from time import perf_counter
from llm.config import ModelTarget
from llm.providers.base import ProviderAdapter,ProviderError,ProviderErrorKind,ProviderRequest,ProviderResponse

class ProviderService:
    def __init__(self,adapter:ProviderAdapter,primary:ModelTarget,fallback:ModelTarget|None,*,purpose_targets:dict[str,ModelTarget]|None=None,diagnostics=None):
        self._adapter=adapter
        self._primary=primary
        self._fallback=fallback
        self._purpose_targets=dict(purpose_targets or {})
        self._diagnostics=diagnostics

    async def infer(self,request:ProviderRequest)->ProviderResponse:
        primary=self._purpose_targets.get(request.purpose,self._primary)
        try:
            return await self._observed(request,primary,1,False)
        except ProviderError as error:
            if self._fallback is None or not self._eligible_for_fallback(error):
                raise
            return await self._observed(request,self._fallback,2,True)

    async def _observed(self,request,target,attempt,fallback):
        started=perf_counter()
        try:
            response=await self._infer_target(request,target)
        except ProviderError as error:
            self._record(purpose=request.purpose,outcome="ERROR",provider=error.provider,model=error.model,
                         attempt=attempt,fallback=fallback,latency_ms=(perf_counter()-started)*1000,
                         valid=False,error_code=error.kind.value)
            raise
        self._record(purpose=request.purpose,outcome="SUCCESS",provider=response.provider,model=response.model,
                     attempt=attempt,fallback=fallback,latency_ms=(perf_counter()-started)*1000,
                     input_tokens=response.usage.input_tokens,output_tokens=response.usage.output_tokens,valid=True)
        return response

    def _record(self,**kwargs):
        if self._diagnostics is not None:
            self._diagnostics.record(**kwargs)

    async def _infer_target(self,request,target):
        return await self._adapter.infer(replace(request,model=f"{target.provider}/{target.model}"))

    @staticmethod
    def _eligible_for_fallback(error):
        if error.kind in {ProviderErrorKind.TIMEOUT,ProviderErrorKind.UNAVAILABLE,
                          ProviderErrorKind.CONNECTION,ProviderErrorKind.INVALID_STRUCTURED_OUTPUT}:
            return True
        return error.kind is ProviderErrorKind.RATE_LIMITED and error.retryable
