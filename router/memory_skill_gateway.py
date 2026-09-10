from __future__ import annotations

import re
from typing import Any

from router.lifecycle.service import ContextResult, LifecycleDecision
from router.memory_client import MemoryApiError, MemoryUnavailable
from shared.protocol.memory import (
    MemoryScope,
    SemanticMemoryCreate,
    SemanticMemoryDelete,
    SemanticMemorySource,
    SemanticMemorySupersede,
    SemanticMemoryType,
    SemanticSearchRequest,
)
from shared.protocol.requests import NyraRequest


_STOPWORDS = {
    "a", "an", "the", "my", "mine", "me", "of", "to", "that",
    "la", "il", "lo", "i", "gli", "le", "mia", "mio", "mie", "miei",
    "di", "che",
}


def _lang(language: str) -> str:
    return "it" if language.split("-", 1)[0].lower() == "it" else "en"


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", value.casefold())
        if token not in _STOPWORDS
    }


def _lexically_authorized(query: str, content: str) -> bool:
    query_tokens = _tokens(query)
    content_tokens = _tokens(content)
    return bool(query_tokens) and query_tokens <= content_tokens


def _identity_user_id(context: ContextResult) -> str | None:
    identity = context.data.get("identity")
    if not isinstance(identity, dict):
        return None
    user_id = identity.get("user_id")
    if not isinstance(user_id, str) or not user_id or user_id == "guest":
        return None
    return user_id


def _localized(language: str, key: str) -> str:
    it = _lang(language) == "it"
    values = {
        "remembered": ("Ricordato.", "Remembered."),
        "forgotten": ("Memoria eliminata.", "Memory deleted."),
        "superseded": ("Memoria aggiornata.", "Memory updated."),
        "not_found": (
            "Non ho trovato una memoria corrispondente.",
            "I could not find a matching memory.",
        ),
        "clarify": (
            "Ho trovato più memorie possibili. Quale intendi?",
            "I found multiple possible memories. Which one do you mean?",
        ),
        "clarify_again": (
            "Non riesco ancora a capire quale memoria intendi.",
            "I still cannot tell which memory you mean.",
        ),
    }
    return values[key][0 if it else 1]


class MemorySkillGateway:
    """Router-owned authorization and mutation gateway for explicit memory Skills."""

    def __init__(self, memory_client) -> None:
        self.memory_client = memory_client

    @staticmethod
    def _idempotency_key(request: NyraRequest, operation: str) -> str:
        request_id = request.request_id or request.origin_request_id or "job"
        return f"{request_id}:{operation}"[:255]

    async def _search(
        self,
        *,
        request: NyraRequest,
        user_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        payload = SemanticSearchRequest(
            query=query,
            scopes=[MemoryScope.USER],
            owner_user_id=user_id,
            limit=10,
            minimum_similarity=0.35,
        )
        data = await self.memory_client.json(
            "POST",
            "/v1/semantic/search",
            payload=payload.model_dump(mode="json"),
        )
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        authorized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("scope") != MemoryScope.USER.value:
                continue
            if item.get("owner_user_id") != user_id:
                continue
            content = item.get("content")
            memory_id = item.get("memory_id")
            if not isinstance(content, str) or not isinstance(memory_id, str):
                continue
            # Similarity score is only discovery/ranking evidence.
            # Destructive authorization requires deterministic lexical evidence.
            if _lexically_authorized(query, content):
                authorized.append(
                    {
                        "memory_id": memory_id,
                        "content": content,
                    }
                )
        return authorized

    async def _delete(
        self,
        *,
        request: NyraRequest,
        memory_id: str,
    ) -> None:
        payload = SemanticMemoryDelete(
            idempotency_key=self._idempotency_key(request, f"forget:{memory_id}")
        )
        await self.memory_client.json(
            "DELETE",
            f"/v1/semantic/memories/{memory_id}",
            payload=payload.model_dump(mode="json"),
        )

    async def _supersede(
        self,
        *,
        request: NyraRequest,
        user_id: str,
        memory_id: str,
        replacement: str,
        memory_type: str | None,
    ) -> None:
        try:
            parsed_type = SemanticMemoryType(memory_type or SemanticMemoryType.NOTE.value)
        except ValueError:
            parsed_type = SemanticMemoryType.NOTE

        replacement_payload = SemanticMemoryCreate(
            memory_type=parsed_type,
            scope=MemoryScope.USER,
            owner_user_id=user_id,
            content=replacement,
            source=SemanticMemorySource.USER_EXPLICIT,
            idempotency_key=self._idempotency_key(
                request, f"supersede-replacement:{memory_id}"
            ),
        )
        payload = SemanticMemorySupersede(
            replacement=replacement_payload,
            idempotency_key=self._idempotency_key(
                request, f"supersede:{memory_id}"
            ),
        )
        await self.memory_client.json(
            "POST",
            f"/v1/semantic/memories/{memory_id}/supersede",
            payload=payload.model_dump(mode="json"),
        )

    async def _remember(
        self,
        *,
        request: NyraRequest,
        user_id: str,
        operation: dict[str, Any],
    ) -> LifecycleDecision:
        content = operation.get("content")
        if not isinstance(content, str) or not content.strip():
            return LifecycleDecision.failed("INVALID_MEMORY_CONTENT")
        try:
            memory_type = SemanticMemoryType(
                operation.get("memory_type", SemanticMemoryType.NOTE.value)
            )
        except ValueError:
            memory_type = SemanticMemoryType.NOTE

        payload = SemanticMemoryCreate(
            memory_type=memory_type,
            scope=MemoryScope.USER,
            owner_user_id=user_id,
            content=content,
            source=SemanticMemorySource.USER_EXPLICIT,
            idempotency_key=self._idempotency_key(request, "remember"),
        )
        await self.memory_client.json(
            "POST",
            "/v1/semantic/memories",
            payload=payload.model_dump(mode="json"),
        )
        return LifecycleDecision.completed(
            _localized(request.language, "remembered")
        )

    @staticmethod
    def _selection_index(selection: str) -> int | None:
        normalized = selection.strip().casefold()
        mapping = {
            "1": 0, "first": 0, "the first": 0, "prima": 0, "la prima": 0,
            "2": 1, "second": 1, "the second": 1, "seconda": 1, "la seconda": 1,
            "3": 2, "third": 2, "the third": 2, "terza": 2, "la terza": 2,
        }
        return mapping.get(normalized)

    def _resolve_pending_candidate(
        self,
        selection: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        index = self._selection_index(selection)
        if index is not None and index < len(candidates):
            return candidates[index]

        matches = [
            candidate
            for candidate in candidates
            if isinstance(candidate.get("content"), str)
            and _lexically_authorized(selection, candidate["content"])
        ]
        return matches[0] if len(matches) == 1 else None

    async def _execute_selected(
        self,
        *,
        request: NyraRequest,
        user_id: str,
        operation: str,
        candidate: dict[str, Any],
        replacement: str | None,
        memory_type: str | None,
    ) -> LifecycleDecision:
        memory_id = candidate.get("memory_id")
        if not isinstance(memory_id, str):
            return LifecycleDecision.failed("INVALID_MEMORY_TARGET")

        if operation == "FORGET":
            await self._delete(request=request, memory_id=memory_id)
            return LifecycleDecision.completed(
                _localized(request.language, "forgotten")
            )

        if operation == "SUPERSEDE":
            if not isinstance(replacement, str) or not replacement.strip():
                return LifecycleDecision.failed("INVALID_MEMORY_REPLACEMENT")
            await self._supersede(
                request=request,
                user_id=user_id,
                memory_id=memory_id,
                replacement=replacement,
                memory_type=memory_type,
            )
            return LifecycleDecision.completed(
                _localized(request.language, "superseded")
            )

        return LifecycleDecision.failed("INVALID_MEMORY_OPERATION")

    async def execute(
        self,
        *,
        request: NyraRequest,
        context: ContextResult,
        operation: dict[str, Any],
        pending_state: dict[str, Any] | None = None,
    ) -> LifecycleDecision:
        user_id = _identity_user_id(context)
        if user_id is None:
            return LifecycleDecision.failed("MEMORY_USER_IDENTITY_REQUIRED")

        try:
            name = operation.get("operation")

            if name == "REMEMBER":
                return await self._remember(
                    request=request,
                    user_id=user_id,
                    operation=operation,
                )

            if name == "RESOLVE_CLARIFICATION":
                pending = pending_state or {}
                if pending.get("kind") != "memory_management_clarification":
                    return LifecycleDecision.failed(
                        "INVALID_MEMORY_CLARIFICATION_STATE"
                    )
                candidates = pending.get("candidates")
                selection = operation.get("selection")
                if not isinstance(candidates, list) or not isinstance(selection, str):
                    return LifecycleDecision.failed(
                        "INVALID_MEMORY_CLARIFICATION_STATE"
                    )
                candidate = self._resolve_pending_candidate(selection, candidates)
                if candidate is None:
                    return LifecycleDecision.needs_clarification(
                        _localized(request.language, "clarify_again"),
                        pending,
                    )
                return await self._execute_selected(
                    request=request,
                    user_id=user_id,
                    operation=str(pending.get("operation")),
                    candidate=candidate,
                    replacement=(
                        pending.get("replacement")
                        if isinstance(pending.get("replacement"), str)
                        else None
                    ),
                    memory_type=(
                        pending.get("memory_type")
                        if isinstance(pending.get("memory_type"), str)
                        else None
                    ),
                )

            if name not in {"FORGET", "SUPERSEDE"}:
                return LifecycleDecision.failed("INVALID_MEMORY_OPERATION")

            query = operation.get("query")
            if not isinstance(query, str) or not query.strip():
                return LifecycleDecision.failed("INVALID_MEMORY_QUERY")

            candidates = await self._search(
                request=request,
                user_id=user_id,
                query=query,
            )
            if not candidates:
                return LifecycleDecision.failed("MEMORY_NOT_FOUND")
            if len(candidates) > 1:
                return LifecycleDecision.needs_clarification(
                    _localized(request.language, "clarify"),
                    {
                        "kind": "memory_management_clarification",
                        "operation": name,
                        "query": query,
                        "replacement": operation.get("replacement"),
                        "memory_type": operation.get("memory_type"),
                        "candidates": candidates,
                    },
                )

            return await self._execute_selected(
                request=request,
                user_id=user_id,
                operation=name,
                candidate=candidates[0],
                replacement=(
                    operation.get("replacement")
                    if isinstance(operation.get("replacement"), str)
                    else None
                ),
                memory_type=(
                    operation.get("memory_type")
                    if isinstance(operation.get("memory_type"), str)
                    else None
                ),
            )
        except MemoryUnavailable:
            return LifecycleDecision.failed("MEMORY_UNAVAILABLE")
        except MemoryApiError as exc:
            if exc.status_code == 404:
                return LifecycleDecision.failed("MEMORY_NOT_FOUND")
            if exc.status_code in {502, 503, 504}:
                return LifecycleDecision.failed("MEMORY_UNAVAILABLE")
            return LifecycleDecision.failed(exc.code or "MEMORY_FAILED")
