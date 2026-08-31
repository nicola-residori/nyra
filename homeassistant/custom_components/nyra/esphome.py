from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass

from typing import Any

from shared.protocol.events import IdentityFeedback

SOURCE_ID_NAME = "Nyra Source ID"
STATUS_RING_NAME = "Nyra Status Ring"
CLOSE_FEEDBACK_NAME = "Nyra Close Feedback"



def _entity_value(entity, name: str):
    if isinstance(entity, dict):
        return entity.get(name)
    return getattr(entity, name, None)


def resolve_nyra_source_id(
    satellite_id: str,
    entities,
    states: dict[str, str],
) -> str | None:
    """Resolve an HA Assist Satellite entity to its stable Nyra source ID."""

    satellite_device_id = None
    for entity in entities:
        if (
            _entity_value(entity, "entity_id") == satellite_id
            and _entity_value(entity, "platform") == "esphome"
        ):
            satellite_device_id = _entity_value(entity, "device_id")
            break

    if not satellite_device_id:
        return None

    for entity in entities:
        if (
            _entity_value(entity, "device_id") == satellite_device_id
            and _entity_value(entity, "platform") == "esphome"
            and _entity_value(entity, "original_name") == SOURCE_ID_NAME
        ):
            entity_id = _entity_value(entity, "entity_id")
            source_id = states.get(entity_id)
            if not source_id:
                return None
            source_id = source_id.strip()
            if not source_id or source_id in {"unknown", "unavailable"}:
                return None
            return source_id

    return None




@dataclass(frozen=True)
class SpeakerTarget:
    light_entity: str
    close_feedback_button: str | None = None


def _value(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def discover_speaker_targets(
    devices: Iterable[Any],
    entities: Iterable[Any],
    states: Mapping[str, str],
) -> dict[str, SpeakerTarget]:
    """Discover Nyra speaker outputs from Home Assistant registry data.

    The read-only ``Nyra Source ID`` text sensor is the stable join key.
    Entity IDs and device display names are intentionally not part of the
    contract because users may rename them in Home Assistant.
    """

    known_devices = {
        _value(device, "id")
        for device in devices
        if _value(device, "id")
    }

    by_device: dict[str, dict[str, str]] = {}
    for entity in entities:
        if _value(entity, "platform") != "esphome":
            continue

        device_id = _value(entity, "device_id")
        if not device_id or device_id not in known_devices:
            continue

        original_name = _value(entity, "original_name")
        entity_id = _value(entity, "entity_id")
        if not original_name or not entity_id:
            continue

        if original_name == SOURCE_ID_NAME:
            by_device.setdefault(device_id, {})["source"] = entity_id
        elif original_name == STATUS_RING_NAME:
            by_device.setdefault(device_id, {})["ring"] = entity_id
        elif original_name == CLOSE_FEEDBACK_NAME:
            by_device.setdefault(device_id, {})["close"] = entity_id

    targets: dict[str, SpeakerTarget] = {}
    for parts in by_device.values():
        source_entity = parts.get("source")
        ring_entity = parts.get("ring")
        if not source_entity or not ring_entity:
            continue

        source_id = states.get(source_entity)
        if not source_id:
            continue

        source_id = source_id.strip()
        if not source_id:
            continue

        targets[source_id] = SpeakerTarget(
            light_entity=ring_entity,
            close_feedback_button=parts.get("close"),
        )

    return targets


class EspHomeSpeakerOutput:
    """Render Nyra semantic feedback through standard Home Assistant services.

    ESPHome owns the concrete effects and audio implementation. In particular,
    wake-word opening audio remains entirely local to the speaker firmware.
    """

    def __init__(
        self,
        targets: dict[str, SpeakerTarget],
        call_service: Callable[[str, str, dict], Awaitable[None]],
        resolve_targets: Callable[
            [], Awaitable[dict[str, SpeakerTarget]]
        ] | None = None,
    ):
        self._targets = targets
        self._call_service = call_service
        self._resolve_targets = resolve_targets

    async def _target(self, source_id: str) -> SpeakerTarget | None:
        target = self._targets.get(source_id)
        if target is not None or self._resolve_targets is None:
            return target

        self._targets = await self._resolve_targets()
        return self._targets.get(source_id)

    async def _effect(self, source_id: str, effect: str) -> None:
        target = await self._target(source_id)
        if target:
            await self._call_service(
                "light",
                "turn_on",
                {"entity_id": target.light_entity, "effect": effect},
            )

    async def set_idle(self, source_id: str) -> None:
        target = await self._target(source_id)
        if target:
            await self._call_service(
                "light",
                "turn_off",
                {"entity_id": target.light_entity},
            )

    async def pulse_white_fast(self, source_id: str) -> None:
        await self._effect(source_id, "Pulse Fast")

    async def comet_warm_white(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_identifying_warm_white_comet")

    async def blink_identity(
        self,
        source_id: str,
        feedback: IdentityFeedback,
        count: int,
    ) -> None:
        effect = {
            IdentityFeedback.RECOGNIZED: "nyra_identity_green_2blink",
            IdentityFeedback.NOT_RECOGNIZED: "nyra_identity_red_2blink",
            IdentityFeedback.IDENTITY_CHANGED: "nyra_identity_blue_2blink",
        }[feedback]
        await self._effect(source_id, effect)

    async def comet_turquoise(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_processing_local_turquoise_comet")

    async def comet_rainbow(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_processing_global_rainbow_comet")

    async def comet_yellow(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_using_tool_yellow_comet")

    async def speaking_purple(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_speaking_purple_audio")

    async def error_red(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_error_red")

    async def close_feedback(self, source_id: str) -> None:
        target = await self._target(source_id)
        if target and target.close_feedback_button:
            await self._call_service(
                "button",
                "press",
                {"entity_id": target.close_feedback_button},
            )
