from __future__ import annotations

import json
from copy import deepcopy
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
            strict_compatible = self._is_strict_schema_compatible(request.response_schema)
            provider_schema = (
                self._strict_response_schema(request.response_schema)
                if strict_compatible
                else deepcopy(request.response_schema)
            )
            completion_args = {
                "model": request.model,
                "messages": [dict(message) for message in request.messages],
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "nyra_response",
                        "strict": strict_compatible,
                        "schema": provider_schema,
                    },
                },
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
    def _is_strict_schema_compatible(schema: dict[str, Any]) -> bool:
        # Pydantic Any is emitted as an unconstrained schema such as
        # {"title": "Value"}. Inspect only actual schema nodes: mappings
        # under properties/$defs are containers whose values are schemas.
        structural_keywords = {
            "$ref", "type", "anyOf", "oneOf", "allOf", "enum", "const",
            "properties", "items", "prefixItems",
        }

        def visit(node: Any) -> bool:
            if not isinstance(node, dict):
                return True

            if not any(key in node for key in structural_keywords):
                return False

            # Open mappings (for example dict[str, Any]) cannot be represented
            # faithfully by the provider strict subset. Keep the Nyra schema
            # unchanged and request non-strict JSON-schema output instead.
            if node.get("additionalProperties") is True:
                return False

            properties = node.get("properties")
            if isinstance(properties, dict):
                if not all(visit(child) for child in properties.values()):
                    return False

            definitions = node.get("$defs")
            if isinstance(definitions, dict):
                if not all(visit(child) for child in definitions.values()):
                    return False

            for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
                children = node.get(key)
                if isinstance(children, list):
                    if not all(visit(child) for child in children):
                        return False

            items = node.get("items")
            if isinstance(items, dict) and not visit(items):
                return False

            return True

        return visit(schema)

    @staticmethod
    def _strict_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
        # Build a provider-strict copy without changing Nyra's contract schema.
        strict = deepcopy(schema)

        def normalize(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["required"] = list(properties)
                if node.get("type") == "object":
                    node["additionalProperties"] = False

                # Provider strict schemas reject default siblings on $ref; defaults are not part of the provider contract.
                node.pop("default", None)

                for value in list(node.values()):
                    normalize(value)
            elif isinstance(node, list):
                for value in node:
                    normalize(value)

        normalize(strict)
        return strict

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
