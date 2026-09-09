from __future__ import annotations

import re
from typing import Any

import httpx

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ResolveCandidate,
    ResolveCardinality,
    ResolveResponse,
    ResolveStatus,
    ResolvedResource,
    ResourceReference,
)
from shared.protocol.execution_common import NyraResourceType


_RESOURCE_DOMAIN = {
    NyraResourceType.LIGHT: "light",
    NyraResourceType.SWITCH: "switch",
    NyraResourceType.COVER: "cover",
    NyraResourceType.CLIMATE: "climate",
    NyraResourceType.MEDIA_PLAYER: "media_player",
    NyraResourceType.SCRIPT: "script",
    NyraResourceType.SCENE: "scene",
    NyraResourceType.AUTOMATION: "automation",
}
_DOMAIN_RESOURCE = {domain: resource for resource, domain in _RESOURCE_DOMAIN.items()}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.casefold())
        if token
    }


class HomeAssistantApiClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport = transport

    async def states(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.get("/api/states")
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Home Assistant states response must be a list")
        return [item for item in payload if isinstance(item, dict)]


class HomeAssistantCapabilityPort:
    def __init__(self, client: HomeAssistantApiClient) -> None:
        self.client = client

    async def resolve(
        self,
        reference: ResourceReference,
        trusted_context: dict[str, Any],
        *,
        correlation: CapabilityCorrelation,
    ) -> ResolveResponse:
        states = await self.client.states()
        allowed = trusted_context.get("allowed_resource_ids")
        allowed_ids = (
            {item for item in allowed if isinstance(item, str)}
            if isinstance(allowed, list)
            else None
        )

        query_tokens = _tokens(reference.reference)
        candidates: list[ResolveCandidate] = []

        for native in states:
            entity_id = native.get("entity_id")
            if not isinstance(entity_id, str) or "." not in entity_id:
                continue

            domain, _ = entity_id.split(".", 1)
            resource_type = _DOMAIN_RESOURCE.get(domain)
            if resource_type is None:
                continue
            if (
                reference.resource_type is not None
                and resource_type is not reference.resource_type
            ):
                continue
            if allowed_ids is not None and entity_id not in allowed_ids:
                continue

            attributes = native.get("attributes")
            attributes = attributes if isinstance(attributes, dict) else {}
            friendly_name = attributes.get("friendly_name")
            friendly_name = friendly_name if isinstance(friendly_name, str) else None

            searchable = " ".join(
                value
                for value in (
                    entity_id.replace(".", " ").replace("_", " "),
                    friendly_name or "",
                )
                if value
            )
            searchable_tokens = _tokens(searchable)
            if query_tokens and not query_tokens.issubset(searchable_tokens):
                continue

            score = (
                len(query_tokens & searchable_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            if (
                friendly_name is not None
                and _tokens(friendly_name) == query_tokens
            ):
                score += 1.0
            candidates.append(
                ResolveCandidate(
                    resource=ResolvedResource(
                        resource_id=entity_id,
                        resource_type=resource_type,
                        name=friendly_name,
                    ),
                    score=score,
                )
            )

        candidates.sort(
            key=lambda item: (
                -(item.score or 0.0),
                item.resource.name or "",
                item.resource.resource_id,
            )
        )

        if not candidates:
            status = ResolveStatus.NOT_FOUND
        elif reference.cardinality is ResolveCardinality.MANY:
            status = ResolveStatus.RESOLVED
        elif len(candidates) == 1:
            status = ResolveStatus.RESOLVED
        else:
            status = ResolveStatus.AMBIGUOUS

        return ResolveResponse(
            correlation=correlation,
            status=status,
            reference=reference,
            candidates=candidates,
        )
