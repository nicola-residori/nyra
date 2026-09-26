import json
from types import SimpleNamespace

import pytest

from llm.providers.base import ProviderError, ProviderErrorKind, ProviderRequest
from llm.providers.litellm_adapter import LiteLlmAdapter


def request():
    return ProviderRequest(
        purpose="SEMANTIC",
        model="openai/model-a",
        messages=({"role": "user", "content": "hello"},),
        response_schema={"type": "object"},
    )


@pytest.mark.asyncio
async def test_adapter_normalizes_litellm_response_and_usage():
    async def completion(**kwargs):
        assert kwargs["model"] == "openai/model-a"
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
        assert kwargs["stream"] is False
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"target":{"kind":"NONE"}}')
                )
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=4),
        )

    response = await LiteLlmAdapter(completion=completion).infer(request())

    assert json.loads(response.content)["target"]["kind"] == "NONE"
    assert response.provider == "openai"
    assert response.model == "model-a"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 4


@pytest.mark.asyncio
async def test_adapter_rejects_malformed_structured_output():
    async def completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))],
            usage=None,
        )

    with pytest.raises(ProviderError) as raised:
        await LiteLlmAdapter(completion=completion).infer(request())

    assert raised.value.kind is ProviderErrorKind.INVALID_STRUCTURED_OUTPUT
    assert raised.value.retryable is True


class Timeout(Exception):
    pass


class RateLimitError(Exception):
    status_code = 429


class AuthenticationError(Exception):
    status_code = 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (Timeout("timeout"), ProviderErrorKind.TIMEOUT, True),
        (RateLimitError("rate"), ProviderErrorKind.RATE_LIMITED, True),
        (AuthenticationError("auth"), ProviderErrorKind.OTHER, False),
    ],
)
async def test_adapter_maps_provider_exceptions(exc, kind, retryable):
    async def completion(**kwargs):
        raise exc

    with pytest.raises(ProviderError) as raised:
        await LiteLlmAdapter(completion=completion).infer(request())

    assert raised.value.kind is kind
    assert raised.value.retryable is retryable
