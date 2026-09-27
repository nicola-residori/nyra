from dataclasses import FrozenInstanceError

import pytest

from llm.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


class FakeAdapter(ProviderAdapter):
    async def infer(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            content='{"outcome":"COMPLETED"}',
            provider="fake",
            model=request.model,
            usage=ProviderUsage(input_tokens=12, output_tokens=3),
        )


@pytest.mark.asyncio
async def test_provider_adapter_has_normalized_request_and_response():
    adapter = FakeAdapter()
    response = await adapter.infer(
        ProviderRequest(
            purpose="REASONING",
            model="model-a",
            messages=({"role": "user", "content": "hello"},),
            response_schema={"type": "object"},
        )
    )

    assert response.provider == "fake"
    assert response.model == "model-a"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3


def test_provider_contract_is_immutable():
    request = ProviderRequest(
        purpose="SEMANTIC",
        model="model-a",
        messages=(),
        response_schema={"type": "object"},
    )

    with pytest.raises(FrozenInstanceError):
        request.model = "other"


def test_provider_errors_are_normalized():
    error = ProviderError(
        kind=ProviderErrorKind.TIMEOUT,
        provider="openai",
        model="model-a",
        message="timed out",
        retryable=True,
    )

    assert error.kind is ProviderErrorKind.TIMEOUT
    assert error.retryable is True
