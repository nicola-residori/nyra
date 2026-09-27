from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from llm.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


Completion = Callable[..., Awaitable[Any]]


class LiteLlmAdapter(ProviderAdapter):
    def __init__(self, completion: Completion | None = None, api_keys: dict[str, str] | None = None) -> None:
        if completion is None:
            from litellm import acompletion

            completion = acompletion
        self._completion = completion
        self._api_keys = dict(api_keys or {})

    async def infer(self, request: ProviderRequest) -> ProviderResponse:
        provider, model = self._split_model(request.model)
        try:
            completion_args = {
                "model": request.model,
                "messages": [dict(message) for message in request.messages],
                "stream": False,
            }
            api_key = self._api_keys.get(provider)
            if api_key:
                completion_args["api_key"] = api_key
            raw = await self._completion(**completion_args)
        except Exception as exc:
            raise self._map_error(exc, provider, model) from exc

        try:
            content = raw.choices[0].message.content
            if not isinstance(content, str):
                raise ValueError("provider response content is not text")
            json.loads(content)
        except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                ProviderErrorKind.INVALID_STRUCTURED_OUTPUT,
                provider,
                model,
                "provider returned invalid structured output",
                True,
            ) from exc

        usage = getattr(raw, "usage", None)
        return ProviderResponse(
            content=content,
            provider=provider,
            model=model,
            usage=ProviderUsage(
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
            ),
        )

    @staticmethod
    def _split_model(value: str) -> tuple[str, str]:
        provider, separator, model = value.partition("/")
        if not separator or not provider or not model:
            raise ProviderError(
                ProviderErrorKind.OTHER,
                provider or "unknown",
                model or value,
                "provider-qualified model is required",
                False,
            )
        return provider, model

    @staticmethod
    def _map_error(
        exc: Exception, provider: str, model: str
    ) -> ProviderError:
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)

        if name in {"Timeout", "APITimeoutError"} or status == 408:
            kind, retryable = ProviderErrorKind.TIMEOUT, True
        elif name == "RateLimitError" or status == 429:
            kind, retryable = ProviderErrorKind.RATE_LIMITED, True
        elif name in {
            "ServiceUnavailableError",
            "InternalServerError",
            "APIError",
        } or (isinstance(status, int) and status >= 500):
            kind, retryable = ProviderErrorKind.UNAVAILABLE, True
        elif name == "APIConnectionError":
            kind, retryable = ProviderErrorKind.CONNECTION, True
        else:
            kind, retryable = ProviderErrorKind.OTHER, False

        return ProviderError(
            kind=kind,
            provider=provider,
            model=model,
            message=str(exc) or name,
            retryable=retryable,
        )
