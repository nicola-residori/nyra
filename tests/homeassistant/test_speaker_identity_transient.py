import asyncio
from types import SimpleNamespace

from shared.protocol.events import IdentityFeedback, InteractionState
from homeassistant.custom_components.nyra.speaker import SpeakerStateMachine


class _Output:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def call(*args):
            self.calls.append((name, *args))
        return call


class _GateSleep:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.seconds = None

    async def __call__(self, seconds):
        self.seconds = seconds
        self.started.set()
        await self.release.wait()


def _state(state):
    return SimpleNamespace(state=state, source=SimpleNamespace(id="speaker-a"))


def _identity(feedback):
    return SimpleNamespace(feedback=feedback, source=SimpleNamespace(id="speaker-a"))


def test_identity_feedback_defers_following_visual_until_minimum_window():
    async def scenario():
        output = _Output()
        gate = _GateSleep()
        machine = SpeakerStateMachine(
            output,
            identity_feedback_seconds=0.65,
            sleep=gate,
        )

        await machine.handle_state(_state(InteractionState.PROCESSING_LOCAL))
        await machine.handle_identity(_identity(IdentityFeedback.NOT_RECOGNIZED))
        await gate.started.wait()
        await machine.handle_state(_state(InteractionState.PROCESSING_GLOBAL))

        assert output.calls[-1][0] == "blink_identity"
        assert gate.seconds >= 0.6

        gate.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert output.calls[-1] == ("comet_rainbow", "speaker-a")

    asyncio.run(scenario())
