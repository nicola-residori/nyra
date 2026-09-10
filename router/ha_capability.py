from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    AutomationCreateRequest,
    AutomationCreateResponse,
    AutomationDeleteRequest,
    AutomationDeleteResponse,
    AutomationReadRequest,
    AutomationReadResponse,
    AutomationUpdateRequest,
    AutomationUpdateResponse,
    ResolveCandidate,
    ResolveCardinality,
    ResolveResponse,
    ResolveStatus,
    ExecuteRequest,
    ExecuteResponse,
    ResolvedResource,
    ResourceReference,
)
from shared.protocol.behavior import Behavior, BehaviorActionType, BehaviorLifecycle
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.common import CommonOutcome, ErrorDetail


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

    async def state(self, entity_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.get(f"/api/states/{entity_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    async def invoke(self, domain: str, service: str, entity_id: str, parameters: dict[str, Any]) -> None:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.post(
                f"/api/services/{domain}/{service}",
                json={"entity_id": entity_id, **parameters},
            )
            response.raise_for_status()


    async def automation_list(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.get("/api/nyra/automations")
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Nyra automation list response must be a list")
        return [item for item in payload if isinstance(item, dict)]

    async def automation_read(self, automation_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.get(f"/api/nyra/automations/{automation_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    async def automation_write(
        self,
        automation_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.post(
                f"/api/nyra/automations/{automation_id}",
                json={"config": config},
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Nyra automation write response must be an object")
        return payload

    async def automation_delete(self, automation_id: str) -> bool:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.delete(f"/api/nyra/automations/{automation_id}")
            if response.status_code == 404:
                return False
            response.raise_for_status()
        return True

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


_OPERATION_MAP = {
    (NyraResourceType.LIGHT, NyraOperation.TURN_ON): ("light", "turn_on"),
    (NyraResourceType.LIGHT, NyraOperation.TURN_OFF): ("light", "turn_off"),
    (NyraResourceType.SWITCH, NyraOperation.TURN_ON): ("switch", "turn_on"),
    (NyraResourceType.SWITCH, NyraOperation.TURN_OFF): ("switch", "turn_off"),
    (NyraResourceType.COVER, NyraOperation.OPEN): ("cover", "open_cover"),
    (NyraResourceType.COVER, NyraOperation.CLOSE): ("cover", "close_cover"),
    (NyraResourceType.SCRIPT, NyraOperation.TRIGGER): ("script", "turn_on"),
    (NyraResourceType.SCENE, NyraOperation.TRIGGER): ("scene", "turn_on"),
}



_MANAGED_PREFIX = "[NYRA managed_by=NYRA behavior_b64="

def _automation_id(behavior: Behavior) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", behavior.behavior_id).strip("_")
    return f"nyra_{safe or 'behavior'}"

def _managed_description(behavior: Behavior) -> str:
    raw = behavior.model_dump_json().encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return f"{_MANAGED_PREFIX}{encoded}]"

def _decode_managed_behavior(config: dict[str, Any]) -> Behavior | None:
    description = config.get("description")
    if not isinstance(description, str) or not description.startswith(_MANAGED_PREFIX):
        return None
    encoded = description[len(_MANAGED_PREFIX):]
    if not encoded.endswith("]"):
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded[:-1].encode("ascii"))
        return Behavior.model_validate(json.loads(raw.decode("utf-8")))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

def _is_managed(config: dict[str, Any] | None) -> bool:
    return isinstance(config, dict) and _decode_managed_behavior(config) is not None

def _native_signature(config: dict[str, Any]) -> str:
    actions = list(config.get("actions") or config.get("action") or [])
    if actions and isinstance(actions[-1], dict):
        if actions[-1].get("action") == "nyra.complete_one_shot":
            actions = actions[:-1]
    signature = {
        "triggers": config.get("triggers") or config.get("trigger") or [],
        "conditions": config.get("conditions") or config.get("condition") or [],
        "actions": actions,
    }
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))

def _translate_trigger(kind: str, expression: str) -> dict[str, Any]:
    if kind == "time":
        return {"trigger": "time", "at": expression}
    if kind == "sun" and expression in {"sunrise", "sunset"}:
        return {"trigger": "sun", "event": expression}
    if kind == "event":
        return {"trigger": "event", "event_type": expression}
    raise ValueError("UNSUPPORTED_BEHAVIOR_TRIGGER")

class HomeAssistantCapabilityPort:
    def __init__(self, client: HomeAssistantApiClient) -> None:
        self.client = client

    async def execute(self, request: ExecuteRequest, trusted_context: dict[str, Any]) -> ExecuteResponse:
        allowed = trusted_context.get("allowed_resource_ids")
        if isinstance(allowed, list) and request.resource_id not in {item for item in allowed if isinstance(item, str)}:
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.DENIED, error=ErrorDetail(code="RESOURCE_DENIED"))

        expected_domain = _RESOURCE_DOMAIN.get(request.resource_type)
        if expected_domain is None or not request.resource_id.startswith(expected_domain + "."):
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.NOT_FOUND, error=ErrorDetail(code="RESOURCE_TYPE_MISMATCH"))

        mapping = _OPERATION_MAP.get((request.resource_type, request.operation))
        if mapping is None:
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.UNSUPPORTED, error=ErrorDetail(code="UNSUPPORTED_OPERATION"))

        native = await self.client.state(request.resource_id)
        if native is None or native.get("entity_id") != request.resource_id:
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.NOT_FOUND, error=ErrorDetail(code="RESOURCE_NOT_FOUND"))
        if native.get("state") in {"unavailable", "unknown"}:
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.UNAVAILABLE, error=ErrorDetail(code="RESOURCE_UNAVAILABLE"))

        domain, service = mapping
        try:
            await self.client.invoke(domain, service, request.resource_id, request.parameters)
        except (httpx.TimeoutException, httpx.TransportError):
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.UNKNOWN_OUTCOME, error=ErrorDetail(code="EXECUTION_OUTCOME_UNKNOWN"))
        except httpx.HTTPStatusError:
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.FAILED, error=ErrorDetail(code="HA_EXECUTION_FAILED"))

        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
            result={"resource_id": request.resource_id, "operation": request.operation.value},
        )


    async def _native_behavior_config(
        self,
        behavior: Behavior,
        trusted_context: dict[str, Any],
        *,
        correlation: CapabilityCorrelation,
        automation_id: str,
    ) -> dict[str, Any]:
        if behavior.conditions:
            raise ValueError("UNSUPPORTED_BEHAVIOR_CONDITION")

        triggers = [
            _translate_trigger(item.kind, item.expression)
            for item in behavior.triggers
        ]
        actions: list[dict[str, Any]] = []

        for item in behavior.actions:
            if item.type is BehaviorActionType.DELAY:
                actions.append({"delay": item.delay_seconds})
                continue
            if item.type is BehaviorActionType.WAIT_CONDITION:
                raise ValueError("UNSUPPORTED_WAIT_CONDITION")
            step = item.action
            if step is None:
                raise ValueError("INVALID_BEHAVIOR_ACTION")

            target = step.target.resolved
            if target is None:
                resolved = await self.resolve(
                    ResourceReference(
                        reference=step.target.reference,
                        resource_type=step.target.resource_type,
                        cardinality=ResolveCardinality.ONE,
                    ),
                    trusted_context,
                    correlation=correlation,
                )
                if (
                    resolved.status is not ResolveStatus.RESOLVED
                    or len(resolved.candidates) != 1
                ):
                    raise ValueError(f"BEHAVIOR_TARGET_{resolved.status.value}")
                resource = resolved.candidates[0].resource
                resource_id = resource.resource_id
                resource_type = resource.resource_type
            else:
                resource_id = target.resource_id
                resource_type = target.resource_type

            mapping = _OPERATION_MAP.get((resource_type, step.operation))
            if mapping is None:
                raise ValueError("UNSUPPORTED_BEHAVIOR_OPERATION")
            domain, service = mapping
            action = {
                "action": f"{domain}.{service}",
                "target": {"entity_id": resource_id},
            }
            if step.parameters:
                action["data"] = dict(step.parameters)
            actions.append(action)

        if behavior.lifecycle is BehaviorLifecycle.ONE_SHOT:
            actions.append(
                {
                    "action": "nyra.complete_one_shot",
                    "data": {"automation_id": automation_id},
                }
            )

        return {
            "alias": f"Nyra {behavior.behavior_id}",
            "description": _managed_description(behavior),
            "triggers": triggers,
            "conditions": [],
            "actions": actions,
        }

    async def create_automation(
        self,
        request: AutomationCreateRequest,
        trusted_context: dict[str, Any],
    ) -> AutomationCreateResponse:
        automation_id = _automation_id(request.behavior)
        try:
            native = await self._native_behavior_config(
                request.behavior,
                trusted_context,
                correlation=request.correlation,
                automation_id=automation_id,
            )
            existing = await self.client.automation_list()
            for item in existing:
                if item.get("id") == automation_id:
                    if not _is_managed(item):
                        return AutomationCreateResponse(
                            correlation=request.correlation,
                            outcome=CommonOutcome.DENIED,
                            error=ErrorDetail(code="AUTOMATION_NOT_NYRA_MANAGED"),
                        )
                    return AutomationCreateResponse(
                        correlation=request.correlation,
                        outcome=CommonOutcome.AMBIGUOUS,
                        automation_id=automation_id,
                        behavior=_decode_managed_behavior(item),
                        error=ErrorDetail(code="AUTOMATION_ALREADY_EXISTS"),
                    )
                if _native_signature(item) == _native_signature(native):
                    return AutomationCreateResponse(
                        correlation=request.correlation,
                        outcome=CommonOutcome.AMBIGUOUS,
                        error=ErrorDetail(code="PROBABLE_EQUIVALENT_AUTOMATION"),
                    )
            await self.client.automation_write(automation_id, native)
        except (httpx.TimeoutException, httpx.TransportError):
            return AutomationCreateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNAVAILABLE,
                error=ErrorDetail(code="HA_AUTOMATION_UNAVAILABLE"),
            )
        except httpx.HTTPStatusError:
            return AutomationCreateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.FAILED,
                error=ErrorDetail(code="HA_AUTOMATION_CREATE_FAILED"),
            )
        except ValueError as exc:
            return AutomationCreateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNSUPPORTED,
                error=ErrorDetail(code=str(exc)),
            )
        return AutomationCreateResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
            automation_id=automation_id,
            behavior=request.behavior,
        )

    async def read_automation(
        self,
        request: AutomationReadRequest,
        trusted_context: dict[str, Any],
    ) -> AutomationReadResponse:
        del trusted_context
        try:
            current = await self.client.automation_read(request.automation_id)
        except (httpx.TimeoutException, httpx.TransportError):
            return AutomationReadResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNAVAILABLE,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_UNAVAILABLE"),
            )
        except httpx.HTTPStatusError:
            return AutomationReadResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.FAILED,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_READ_FAILED"),
            )
        if current is None:
            return AutomationReadResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.NOT_FOUND,
                automation_id=request.automation_id,
            )
        behavior = _decode_managed_behavior(current)
        return AutomationReadResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
            automation_id=request.automation_id,
            behavior=behavior,
            managed_by="NYRA" if behavior is not None else None,
        )

    async def update_automation(
        self,
        request: AutomationUpdateRequest,
        trusted_context: dict[str, Any],
    ) -> AutomationUpdateResponse:
        try:
            current = await self.client.automation_read(request.automation_id)
            if current is None:
                return AutomationUpdateResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.NOT_FOUND,
                    automation_id=request.automation_id,
                )
            if not _is_managed(current):
                return AutomationUpdateResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.DENIED,
                    automation_id=request.automation_id,
                    error=ErrorDetail(code="AUTOMATION_NOT_NYRA_MANAGED"),
                )
            native = await self._native_behavior_config(
                request.behavior,
                trusted_context,
                correlation=request.correlation,
                automation_id=request.automation_id,
            )
            await self.client.automation_write(request.automation_id, native)
        except (httpx.TimeoutException, httpx.TransportError):
            return AutomationUpdateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNAVAILABLE,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_UNAVAILABLE"),
            )
        except httpx.HTTPStatusError:
            return AutomationUpdateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.FAILED,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_UPDATE_FAILED"),
            )
        except ValueError as exc:
            return AutomationUpdateResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNSUPPORTED,
                automation_id=request.automation_id,
                error=ErrorDetail(code=str(exc)),
            )
        return AutomationUpdateResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
            automation_id=request.automation_id,
            behavior=request.behavior,
        )

    async def delete_automation(
        self,
        request: AutomationDeleteRequest,
        trusted_context: dict[str, Any],
    ) -> AutomationDeleteResponse:
        del trusted_context
        try:
            current = await self.client.automation_read(request.automation_id)
            if current is None:
                return AutomationDeleteResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.NOT_FOUND,
                    automation_id=request.automation_id,
                )
            if not _is_managed(current):
                return AutomationDeleteResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.DENIED,
                    automation_id=request.automation_id,
                    error=ErrorDetail(code="AUTOMATION_NOT_NYRA_MANAGED"),
                )
            deleted = await self.client.automation_delete(request.automation_id)
            if not deleted:
                return AutomationDeleteResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.NOT_FOUND,
                    automation_id=request.automation_id,
                )
        except (httpx.TimeoutException, httpx.TransportError):
            return AutomationDeleteResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.UNAVAILABLE,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_UNAVAILABLE"),
            )
        except httpx.HTTPStatusError:
            return AutomationDeleteResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.FAILED,
                automation_id=request.automation_id,
                error=ErrorDetail(code="HA_AUTOMATION_DELETE_FAILED"),
            )
        return AutomationDeleteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
            automation_id=request.automation_id,
        )

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
