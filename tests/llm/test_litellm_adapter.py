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
@pytest.mark.asyncio
async def test_adapter_uses_provider_scoped_api_key_without_putting_it_in_request():
    seen={}
    async def completion(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],usage=None)
    adapter=LiteLlmAdapter(completion=completion,api_keys={"openai":"secret-openai-key"})
    provider_request=request()
    assert not hasattr(provider_request,"api_key")
    await adapter.infer(provider_request)
    assert seen["api_key"]=="secret-openai-key"
    assert "secret-openai-key" not in repr(provider_request)

@pytest.mark.asyncio
async def test_adapter_does_not_reuse_key_for_another_provider():
    seen={}
    async def completion(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],usage=None)
    adapter=LiteLlmAdapter(completion=completion,api_keys={"openai":"secret-openai-key"})
    req=ProviderRequest(purpose="REASONING",model="anthropic/model-b",messages=(),response_schema={})
    await adapter.infer(req)
    assert "api_key" not in seen


@pytest.mark.asyncio
async def test_adapter_sends_json_schema_response_format_to_provider():
    seen={}
    async def completion(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"intent":"query"}'))],
            usage=None,
        )
    req=ProviderRequest(
        purpose="SEMANTIC",
        model="openai/gpt-test",
        messages=({"role":"user","content":"hello"},),
        response_schema={"type":"object","properties":{"intent":{"type":"string"}},"required":["intent"]},
    )
    await LiteLlmAdapter(completion=completion).infer(req)
    assert seen["response_format"] == {
        "type":"json_schema",
        "json_schema":{
            "name":"nyra_response",
            "strict":True,
            "schema":req.response_schema,
        },
    }
