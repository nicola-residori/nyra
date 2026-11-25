"""Home Assistant transport to discovered Nyra firmware command entities."""

import json


def provider_language(requested, preferred, supported):
    """Resolve request language to an advertised provider locale, without changing language."""
    normalize = lambda value: (value or "").replace("_", "-").lower()
    available = {normalize(value): value for value in supported}
    request = normalize(requested)
    if request in available:
        return available[request]
    base = request.split("-", 1)[0]
    # An explicit region is preserved unless the provider advertises a generic language.
    if "-" in request:
        if base in available:
            return available[base]
        raise ValueError("requested TTS locale is unsupported")
    preferred_key = normalize(preferred)
    if preferred_key.split("-", 1)[0] == base and preferred_key in available:
        return available[preferred_key]
    default = {"it": "it-it", "en": "en-us"}.get(base)
    if default in available:
        return available[default]
    candidates = [
        value for key, value in available.items() if key.split("-", 1)[0] == base
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError("requested TTS language is unavailable or ambiguous")


class HomeAssistantAlertBackend:
    def __init__(self, hass, resolve_targets, *, pipeline_id=None):
        self.hass = hass
        self.resolve_targets = resolve_targets
        self.pipeline_id = pipeline_id

    async def _target(self, source):
        return (await self.resolve_targets()).get(source)

    def _state(self, entity):
        state = self.hass.states.get(entity) if entity else None
        return (
            state.state
            if state and state.state not in ("unknown", "unavailable", "")
            else None
        )

    async def available(self, source):
        target = await self._target(source)
        if not target or not target.alert_command_entity:
            return False
        state = self.hass.states.get(target.alert_command_entity)
        return bool(
            state
            and state.state != "unavailable"
            and self._state(target.audio_epoch_entity)
        )

    async def epoch(self, source):
        target = await self._target(source)
        return self._state(target.audio_epoch_entity) if target else None

    async def prepare(self, request):
        if request.alert_kind not in ("call", "notification"):
            return ""
        from homeassistant.components import tts, media_source
        from homeassistant.components.assist_pipeline import async_get_pipeline
        from homeassistant.components.media_player import async_process_play_media_url

        pipeline = async_get_pipeline(self.hass, self.pipeline_id)
        engine = tts.async_resolve_engine(self.hass, pipeline.tts_engine)
        instance = tts.get_engine_instance(self.hass, engine) if engine else None
        if instance is None:
            raise ValueError("TTS engine unavailable")
        language = provider_language(
            request.language, pipeline.tts_language, instance.supported_languages
        )
        options = {}
        if (
            pipeline.tts_voice
            and language.replace("_", "-").lower()
            == (pipeline.tts_language or "").replace("_", "-").lower()
        ):
            options[tts.ATTR_VOICE] = pipeline.tts_voice
        media_id = tts.generate_media_source_id(
            self.hass,
            request.message,
            engine=engine,
            language=language,
            options=options,
        )
        media = await media_source.async_resolve_media(self.hass, media_id, None)
        return async_process_play_media_url(self.hass, media.url)

    async def play(self, request, url, epoch):
        target = await self._target(request.source_id)
        if target is None or not await self.available(request.source_id):
            raise RuntimeError("speaker offline")
        command = {
            "action": "START",
            "job_id": request.job_id,
            "kind": request.alert_kind,
            "epoch": epoch,
            "max_seconds": request.max_seconds,
            "url": url,
        }
        encoded = json.dumps(command, separators=(",", ":"))
        if len(encoded) > 255:
            # ESPHome 2026.8 text entities are limited to 255 characters.
            # Stage URL chunks under the job ID, then atomically START with epoch.
            if len(url) > 2048:
                raise ValueError("TTS URL exceeds firmware buffer")
            for offset in range(0, len(url), 80):
                part = {
                    "action": "URL",
                    "job_id": request.job_id,
                    "part": url[offset : offset + 80],
                    "reset": offset == 0,
                }
                value = json.dumps(part, separators=(",", ":"))
                if len(value) > 255:
                    raise ValueError("encoded URL chunk too long")
                await self.hass.services.async_call(
                    "text",
                    "set_value",
                    {"entity_id": target.alert_command_entity, "value": value},
                    blocking=True,
                )
            command["url"] = ""
            encoded = json.dumps(command, separators=(",", ":"))
        if len(encoded) > 255:
            raise ValueError("audio command exceeds firmware text limit")
        await self.hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": target.alert_command_entity, "value": encoded},
            blocking=True,
        )

    async def stop(self, request):
        target = await self._target(request.source_id)
        if not target or not await self.available(request.source_id):
            raise RuntimeError("speaker offline")
        await self.hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": target.alert_command_entity,
                "value": json.dumps(
                    {"action": "STOP", "job_id": request.job_id}, separators=(",", ":")
                ),
            },
            blocking=True,
        )

    async def status(self, request):
        target = await self._target(request.source_id)
        if not target:
            return None
        state = self._state(target.alert_state_entity)
        if state and state.startswith(request.job_id + "|"):
            return state.split("|", 1)[1]
        return None
