"""Authenticated Router entry point for musical operations."""

from shared.protocol.music import MusicRequest

try:
    from homeassistant.components.http import HomeAssistantView
except ImportError:

    class HomeAssistantView:
        pass


class MusicView(HomeAssistantView):
    url = "/api/nyra/music"
    name = "api:nyra:music"
    requires_auth = True

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def post(self, request):
        from aiohttp import web
        from pydantic import ValidationError

        if self.coordinator is None:
            raise web.HTTPServiceUnavailable()
        try:
            payload = MusicRequest.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise web.HTTPBadRequest() from None
        return self.json(await self.coordinator.handle(payload))
