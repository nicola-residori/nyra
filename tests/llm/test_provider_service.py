import pytest

from llm.config import ModelTarget
from llm.provider_service import ProviderService
from llm.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
)


class ScriptedAdapter(ProviderAdapter):
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def infer(self, request):
        self.calls.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def request():
    return ProviderRequest(
        purpose="REASONING",
        model="caller-value-is-replaced",
        messages=({"role": "user", "content": "hello"},),
        response_schema={"type": "object"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        ProviderErrorKind.TIMEOUT,
        ProviderErrorKind.UNAVAILABLE,
        ProviderErrorKind.CONNECTION,
        ProviderErrorKind.INVALID_STRUCTURED_OUTPUT,
    ],
)
async def test_fallback_on_eligible_technical_failures(kind):
    adapter = ScriptedAdapter(
        [
            ProviderError(kind, "primary", "p-model", "technical failure", True),
            ProviderResponse("{}", "fallback", "f-model"),
        ]
    )
    service = ProviderService(
        adapter,
        ModelTarget("primary", "p-model"),
        ModelTarget("fallback", "f-model"),
    )

    response = await service.infer(request())

    assert response.provider == "fallback"
    assert [call.model for call in adapter.calls] == [
        "primary/p-model",
        "fallback/f-model",
    ]


@pytest.mark.asyncio
async def test_retryable_rate_limit_can_fallback():
    adapter = ScriptedAdapter(
        [
            ProviderError(
                ProviderErrorKind.RATE_LIMITED,
                "primary",
                "p-model",
                "rate limited",
                True,
            ),
            ProviderResponse("{}", "fallback", "f-model"),
        ]
    )
    service = ProviderService(
        adapter,
        ModelTarget("primary", "p-model"),
        ModelTarget("fallback", "f-model"),
    )

    assert (await service.infer(request())).provider == "fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "retryable"),
    [
        (ProviderErrorKind.RATE_LIMITED, False),
        (ProviderErrorKind.OTHER, False),
    ],
)
async def test_noneligible_provider_errors_do_not_fallback(kind, retryable):
    error = ProviderError(kind, "primary", "p-model", "do not fallback", retryable)
    adapter = ScriptedAdapter([error])
    service = ProviderService(
        adapter,
        ModelTarget("primary", "p-model"),
        ModelTarget("fallback", "f-model"),
    )

    with pytest.raises(ProviderError) as raised:
        await service.infer(request())

    assert raised.value is error
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_valid_provider_response_never_triggers_fallback():
    response = ProviderResponse(
        '{"outcome":"FAILED","error":{"code":"reasoning_failed"}}',
        "primary",
        "p-model",
    )
    adapter = ScriptedAdapter([response])
    service = ProviderService(
        adapter,
        ModelTarget("primary", "p-model"),
        ModelTarget("fallback", "f-model"),
    )

    assert await service.infer(request()) is response
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_without_fallback_original_error_is_raised():
    error = ProviderError(
        ProviderErrorKind.TIMEOUT, "primary", "p-model", "timeout", True
    )
    adapter = ScriptedAdapter([error])
    service = ProviderService(adapter, ModelTarget("primary", "p-model"), None)

    with pytest.raises(ProviderError) as raised:
        await service.infer(request())

    assert raised.value is error
