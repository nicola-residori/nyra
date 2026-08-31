import asyncio
import inspect

import homeassistant.custom_components.nyra as nyra


class FakeBus:
    def __init__(self):
        self.listeners = {}

    def async_listen(self, event_type, listener):
        self.listeners[event_type] = listener

        def unsubscribe():
            self.listeners.pop(event_type, None)

        return unsubscribe


class FakeHass:
    def __init__(self):
        self.bus = FakeBus()


class FakeSpeaker:
    def __init__(self):
        self.started = []
        self.ended = []

    async def begin_speaking(self, source_id: str) -> None:
        self.started.append(source_id)

    async def end_speaking(self, source_id: str) -> None:
        self.ended.append(source_id)


class FakeEvent:
    def __init__(self, data):
        self.data = data


def _run(result):
    if result is not None:
        asyncio.run(result)


def test_speaking_lifecycle_listener_targets_only_addressed_source():
    hass = FakeHass()
    speaker = FakeSpeaker()
    unsubscribe = nyra.register_speaking_restore_listener(hass, speaker)

    _run(hass.bus.listeners["esphome.nyra_speaking_started"](
        FakeEvent({"source_id": "speaker-a"})
    ))
    _run(hass.bus.listeners["esphome.nyra_speaking_ended"](
        FakeEvent({"source_id": "speaker-a"})
    ))
    _run(hass.bus.listeners["esphome.nyra_speaking_started"](FakeEvent({})))

    assert speaker.started == ["speaker-a"]
    assert speaker.ended == ["speaker-a"]

    unsubscribe()
    assert "esphome.nyra_speaking_started" not in hass.bus.listeners
    assert "esphome.nyra_speaking_ended" not in hass.bus.listeners


def test_runtime_lifecycle_tracks_and_unsubscribes_speaking_restore_listener():
    assert "speaking_restore_unsubscribe" in nyra.NyraRuntime.__dataclass_fields__
    assert hasattr(nyra, "unregister_speaking_restore_listener")

    calls = []

    class Runtime:
        speaking_restore_unsubscribe = lambda self: calls.append("unsubscribed")

    runtime = Runtime()
    nyra.unregister_speaking_restore_listener(runtime)

    assert calls == ["unsubscribed"]
    assert runtime.speaking_restore_unsubscribe is None


def test_setup_and_unload_wire_speaking_restore_listener_lifecycle():
    setup_source = inspect.getsource(nyra.async_setup_entry)
    unload_source = inspect.getsource(nyra.async_unload_entry)

    assert "register_speaking_restore_listener(hass, speaker)" in setup_source
    assert "unregister_speaking_restore_listener(runtime)" in unload_source
