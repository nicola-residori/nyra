"""Authenticated Router-facing audio adapter endpoint."""

from shared.protocol.alerts import AlertRequest

try:
    from homeassistant.components.http import HomeAssistantView
except ImportError:

    class HomeAssistantView:
        pass


class AlertView(HomeAssistantView):
    url = "/api/nyra/alerts"
    name = "api:nyra:alerts"
    requires_auth = True

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def post(self, request):
        from aiohttp import web
        from pydantic import ValidationError

        if self.coordinator is None:
            raise web.HTTPServiceUnavailable()
        try:
            payload = AlertRequest.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise web.HTTPBadRequest() from None
        return self.json(
            (await self.coordinator.handle(payload)).model_dump(mode="json")
        )
