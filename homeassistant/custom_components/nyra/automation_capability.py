from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .const import DOMAIN

AUTOMATION_COLLECTION_PATH = "/api/nyra/automations"
AUTOMATION_ITEM_PATH = "/api/nyra/automations/{automation_id}"
COMPLETE_ONE_SHOT_SERVICE = "complete_one_shot"


def is_nyra_managed(config: Mapping[str, Any] | None) -> bool:
    if not isinstance(config, Mapping):
        return False
    description = config.get("description")
    return isinstance(description, str) and description.startswith(
        "[NYRA managed_by=NYRA "
    )


class NyraAutomationBackend:
    """Minimal transport adapter over Home Assistant automation storage."""

    def __init__(self, hass) -> None:
        self.hass = hass
        self._lock = asyncio.Lock()

    async def _read_all(self) -> list[dict[str, Any]]:
        from homeassistant.config import AUTOMATION_CONFIG_PATH
        from homeassistant.util.yaml import load_yaml

        path = self.hass.config.path(AUTOMATION_CONFIG_PATH)

        def _read():
            try:
                value = load_yaml(path)
            except FileNotFoundError:
                return []
            return value if isinstance(value, list) else []

        return await self.hass.async_add_executor_job(_read)

    async def _write_all(self, items: list[dict[str, Any]]) -> None:
        from homeassistant.config import AUTOMATION_CONFIG_PATH
        from homeassistant.util.file import write_utf8_file_atomic
        from homeassistant.util.yaml import dump

        path = self.hass.config.path(AUTOMATION_CONFIG_PATH)

        def _write():
            write_utf8_file_atomic(path, dump(items))

        await self.hass.async_add_executor_job(_write)

    async def _reload(self, automation_id: str | None = None) -> None:
        from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
        from homeassistant.const import CONF_ID, SERVICE_RELOAD

        data = {CONF_ID: automation_id} if automation_id else {}
        await self.hass.services.async_call(
            AUTOMATION_DOMAIN,
            SERVICE_RELOAD,
            data,
            blocking=True,
        )

    async def list(self) -> list[dict[str, Any]]:
        async with self._lock:
            return deepcopy(await self._read_all())

    async def read(self, automation_id: str) -> dict[str, Any] | None:
        async with self._lock:
            items = await self._read_all()
            for item in items:
                if isinstance(item, dict) and item.get("id") == automation_id:
                    return deepcopy(item)
            return None

    async def write(
        self,
        automation_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        from homeassistant.components.automation.config import (
            async_validate_config_item,
        )

        validated = deepcopy(config)
        validated.pop("id", None)
        await async_validate_config_item(self.hass, automation_id, validated)
        payload = deepcopy(validated)
        payload["id"] = automation_id

        async with self._lock:
            items = await self._read_all()
            updated = False
            for index, item in enumerate(items):
                if isinstance(item, dict) and item.get("id") == automation_id:
                    items[index] = payload
                    updated = True
                    break
            if not updated:
                items.append(payload)
            await self._write_all(items)

        await self._reload(automation_id)
        return deepcopy(payload)

    async def delete(self, automation_id: str) -> bool:
        async with self._lock:
            items = await self._read_all()
            filtered = [
                item
                for item in items
                if not (
                    isinstance(item, dict)
                    and item.get("id") == automation_id
                )
            ]
            if len(filtered) == len(items):
                return False
            await self._write_all(filtered)

        from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(self.hass)
        entity_id = entity_registry.async_get_entity_id(
            AUTOMATION_DOMAIN,
            AUTOMATION_DOMAIN,
            automation_id,
        )
        if entity_id is not None:
            entity_registry.async_remove(entity_id)
        return True


try:
    from homeassistant.components.http import HomeAssistantView
except ImportError:
    class HomeAssistantView:  # type: ignore[no-redef]
        pass


class NyraAutomationCollectionView(HomeAssistantView):
    url = AUTOMATION_COLLECTION_PATH
    name = "api:nyra:automations"
    requires_auth = True

    def __init__(self, backend: NyraAutomationBackend | None) -> None:
        self.backend = backend

    def configure(self, backend: NyraAutomationBackend | None) -> None:
        self.backend = backend

    async def get(self, request):
        from aiohttp import web

        if self.backend is None:
            raise web.HTTPServiceUnavailable()
        return self.json(await self.backend.list())


class NyraAutomationItemView(HomeAssistantView):
    url = AUTOMATION_ITEM_PATH
    name = "api:nyra:automation"
    requires_auth = True

    def __init__(self, backend: NyraAutomationBackend | None) -> None:
        self.backend = backend

    def configure(self, backend: NyraAutomationBackend | None) -> None:
        self.backend = backend

    async def get(self, request, automation_id: str):
        from aiohttp import web

        if self.backend is None:
            raise web.HTTPServiceUnavailable()
        item = await self.backend.read(automation_id)
        if item is None:
            raise web.HTTPNotFound()
        return self.json(item)

    async def post(self, request, automation_id: str):
        from aiohttp import web

        if self.backend is None:
            raise web.HTTPServiceUnavailable()
        try:
            payload = await request.json()
        except ValueError as exc:
            raise web.HTTPBadRequest() from exc
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest()
        config = payload.get("config")
        if not isinstance(config, dict):
            raise web.HTTPBadRequest()
        return self.json(await self.backend.write(automation_id, config))

    async def delete(self, request, automation_id: str):
        from aiohttp import web

        if self.backend is None:
            raise web.HTTPServiceUnavailable()
        if not await self.backend.delete(automation_id):
            raise web.HTTPNotFound()
        return self.json({"result": "ok"})


async def complete_one_shot(backend, automation_id: str) -> bool:
    current = await backend.read(automation_id)
    if not is_nyra_managed(current):
        return False
    return await backend.delete(automation_id)


def register_automation_capability(hass) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    backend = NyraAutomationBackend(hass)

    collection = domain_data.get("automation_collection_view")
    item = domain_data.get("automation_item_view")

    if isinstance(collection, NyraAutomationCollectionView):
        collection.configure(backend)
    else:
        collection = NyraAutomationCollectionView(backend)
        hass.http.register_view(collection)
        domain_data["automation_collection_view"] = collection

    if isinstance(item, NyraAutomationItemView):
        item.configure(backend)
    else:
        item = NyraAutomationItemView(backend)
        hass.http.register_view(item)
        domain_data["automation_item_view"] = item

    if not hass.services.has_service(DOMAIN, COMPLETE_ONE_SHOT_SERVICE):
        async def _complete_one_shot(call):
            automation_id = call.data.get("automation_id")
            if not isinstance(automation_id, str) or not automation_id:
                return
            await complete_one_shot(backend, automation_id)

        hass.services.async_register(
            DOMAIN,
            COMPLETE_ONE_SHOT_SERVICE,
            _complete_one_shot,
        )


def disable_automation_capability(hass) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    collection = domain_data.get("automation_collection_view")
    item = domain_data.get("automation_item_view")
    if isinstance(collection, NyraAutomationCollectionView):
        collection.configure(None)
    if isinstance(item, NyraAutomationItemView):
        item.configure(None)
    if hass.services.has_service(DOMAIN, COMPLETE_ONE_SHOT_SERVICE):
        hass.services.async_remove(DOMAIN, COMPLETE_ONE_SHOT_SERVICE)
