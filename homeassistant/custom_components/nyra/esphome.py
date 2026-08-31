from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shared.protocol.events import IdentityFeedback


@dataclass(frozen=True)
class SpeakerTarget:
    light_entity: str
    close_feedback_button: str | None = None


class EspHomeSpeakerOutput:
    """Render Nyra semantic feedback through standard Home Assistant services.

    ESPHome owns the concrete effects and audio implementation. In particular,
    wake-word opening audio remains entirely local to the speaker firmware.
    """

    def __init__(
        self,
        targets: dict[str, SpeakerTarget],
        call_service: Callable[[str, str, dict], Awaitable[None]],
    ):
        self._targets = targets
        self._call_service = call_service

    def _target(self, source_id: str) -> SpeakerTarget | None:
        return self._targets.get(source_id)

    async def _effect(self, source_id: str, effect: str) -> None:
        target = self._target(source_id)
        if target:
            await self._call_service(
                "light", "turn_on", {"entity_id": target.light_entity, "effect": effect}
            )

    async def set_idle(self, source_id: str) -> None:
        target = self._target(source_id)
        if target:
            await self._call_service("light", "turn_off", {"entity_id": target.light_entity})

    async def pulse_white_fast(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_listening_white_fast")

    async def comet_warm_white(self, source_id: str) -> None:
        await self._effect(source_id, "nyra_identifying_warm_white_comet")

    async def blink_identity(self, source_id: str, feedback: IdentityFeedback, count: int) -> None:
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
        target = self._target(source_id)
        if target and target.close_feedback_button:
            # Firmware button performs the atomic closing sound + blue blink sequence.
            await self._call_service(
                "button", "press", {"entity_id": target.close_feedback_button}
            )
