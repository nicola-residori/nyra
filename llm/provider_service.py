from __future__ import annotations

from dataclasses import replace

from llm.config import ModelTarget
from llm.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
)


class ProviderService:
    def __init__(
        self,
        adapter: ProviderAdapter,
        primary: ModelTarget,
        fallback: ModelTarget | None,
    ) -> None:
        self._adapter = adapter
        self._primary = primary
        self._fallback = fallback

    async def infer(self, request: ProviderRequest) -> ProviderResponse:
        try:
            return await self._infer_target(request, self._primary)
        except ProviderError as error:
            if self._fallback is None or not self._eligible_for_fallback(error):
                raise
            return await self._infer_target(request, self._fallback)

    async def _infer_target(
        self, request: ProviderRequest, target: ModelTarget
    ) -> ProviderResponse:
        provider_model = f"{target.provider}/{target.model}"
        return await self._adapter.infer(replace(request, model=provider_model))

    @staticmethod
    def _eligible_for_fallback(error: ProviderError) -> bool:
        if error.kind in {
            ProviderErrorKind.TIMEOUT,
            ProviderErrorKind.UNAVAILABLE,
            ProviderErrorKind.CONNECTION,
            ProviderErrorKind.INVALID_STRUCTURED_OUTPUT,
        }:
            return True
        return (
            error.kind is ProviderErrorKind.RATE_LIMITED and error.retryable
        )
