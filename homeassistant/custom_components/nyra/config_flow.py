from __future__ import annotations

from typing import Any

from .const import CONF_INGRESS_TOKEN, CONF_ROUTER_URL, DEFAULT_ROUTER_URL, DOMAIN


def normalize_router_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("router URL must start with http:// or https://")
    return value


async def async_validate_input(router_url: str, ingress_token: str | None, client_factory) -> dict[str, Any]:
    url = normalize_router_url(router_url)
    client = client_factory(url, ingress_token or None)
    try:
        if not await client.async_ready():
            raise ConnectionError("Nyra Router is not ready")
    finally:
        await client.async_close()
    return {CONF_ROUTER_URL: url, CONF_INGRESS_TOKEN: ingress_token or ""}


try:
    import voluptuous as vol
    from homeassistant import config_entries
except ImportError:  # keep pure helpers importable in the repository test environment
    config_entries = None
else:
    class NyraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
        VERSION = 1

        async def async_step_user(self, user_input=None):
            from homeassistant.helpers.httpx_client import get_async_client
            from .client import NyraRouterClient

            errors = {}
            if user_input is not None:
                async_client = get_async_client(self.hass)
                try:
                    data = await async_validate_input(
                        user_input[CONF_ROUTER_URL],
                        user_input.get(CONF_INGRESS_TOKEN),
                        lambda url, token: NyraRouterClient(url, token, client=async_client),
                    )
                except (ConnectionError, ValueError):
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title="Nyra", data=data)
            schema = vol.Schema({
                vol.Required(CONF_ROUTER_URL, default=DEFAULT_ROUTER_URL): str,
                vol.Optional(CONF_INGRESS_TOKEN, default=""): str,
            })
            return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
