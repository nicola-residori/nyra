from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.custom_components.nyra.users import (
    AuthenticatedUserReference,
    async_resolve_user_reference,
    async_sync_user_reference,
)


@pytest.mark.asyncio
async def test_resolver_reads_name_from_home_assistant_auth_only():
    auth = SimpleNamespace(
        async_get_user=AsyncMock(
            return_value=SimpleNamespace(id="ha-1", name="  Nicola  ")
        )
    )
    reference = await async_resolve_user_reference(
        SimpleNamespace(auth=auth), "ha-1"
    )

    assert reference == AuthenticatedUserReference("ha-1", "Nicola")
    auth.async_get_user.assert_awaited_once_with("ha-1")


@pytest.mark.asyncio
async def test_resolver_preserves_id_when_user_or_name_is_missing():
    missing = SimpleNamespace(
        auth=SimpleNamespace(async_get_user=AsyncMock(return_value=None))
    )
    blank = SimpleNamespace(
        auth=SimpleNamespace(
            async_get_user=AsyncMock(
                return_value=SimpleNamespace(id="ha-1", name="   ")
            )
        )
    )

    assert await async_resolve_user_reference(missing, "ha-1") == (
        AuthenticatedUserReference("ha-1", None)
    )
    assert await async_resolve_user_reference(blank, "ha-1") == (
        AuthenticatedUserReference("ha-1", None)
    )


@pytest.mark.asyncio
async def test_best_effort_sync_never_blocks_the_caller():
    class Client:
        async def async_sync_user_reference(self, **payload):
            raise RuntimeError("router unavailable")

    synced = await async_sync_user_reference(
        Client(), AuthenticatedUserReference("ha-1", "Nicola")
    )
    missing_name = await async_sync_user_reference(
        Client(), AuthenticatedUserReference("ha-1", None)
    )

    assert synced is False
    assert missing_name is False
