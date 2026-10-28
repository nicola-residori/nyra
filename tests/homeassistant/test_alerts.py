import asyncio
import copy
import pytest
from shared.protocol.alerts import AlertRequest, AlertState
from homeassistant.custom_components.nyra.alerts import AlertCoordinator


class Backend:
    def __init__(self):
        self.commands = []
        self.offline = set()
        self.gate = None
        self.report = {}

    async def available(self, source):
        return source not in self.offline

    async def epoch(self, source):
        return "boot-1"

    async def prepare(self, request):
        if self.gate:
            await self.gate.wait()
        return "http://ha/audio.wav"

    async def play(self, request, url, epoch):
        self.commands.append(("play", request.job_id, request.source_id, epoch))

    async def stop(self, request):
        self.commands.append(("stop", request.job_id, request.source_id))

    async def status(self, request):
        return self.report.get(request.job_id)


class Disk:
    def __init__(self):
        self.data = {}

    async def save(self, data):
        self.data = copy.deepcopy(data)


async def drain():
    for _ in range(5):
        await asyncio.sleep(0)


def req(action="START", job="job_one", source="a"):
    return AlertRequest(action=action, job_id=job, source_id=source)


@pytest.mark.asyncio
async def test_acceptance_actual_playback_and_persistent_deduplication():
    backend = Backend()
    disk = Disk()
    co = AlertCoordinator(backend, disk.save)
    assert (await co.handle(req())).state == AlertState.ACCEPTED
    await drain()
    assert len(backend.commands) == 1
    assert (await co.handle(req())).state == AlertState.ACCEPTED
    await co.event("a", "job_one", "PLAYING")
    assert (await co.handle(req("STATUS"))).state == AlertState.PLAYING
    await co.event("a", "job_one", "COMPLETED")
    assert (await co.handle(req("STATUS"))).state == AlertState.COMPLETED
    restored = AlertCoordinator(backend, disk.save, records=disk.data)
    await restored.restore()
    assert (await restored.handle(req())).state == AlertState.COMPLETED
    assert len(backend.commands) == 1
    await co.shutdown()
    await restored.shutdown()


@pytest.mark.asyncio
async def test_wake_cancels_slow_tts_and_invalidates_conversation_generation():
    backend = Backend()
    backend.gate = asyncio.Event()
    co = AlertCoordinator(backend, Disk().save)
    generation = co.generation("a")
    await co.handle(req())
    await drain()
    assert co.generation("a") != generation
    await co.wake("a")
    backend.gate.set()
    await drain()
    assert not any(c[0] == "play" for c in backend.commands)
    assert (await co.handle(req("STATUS"))).state == AlertState.STOPPED
    await co.shutdown()


@pytest.mark.asyncio
async def test_source_isolation_busy_and_stale_callback():
    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)
    await co.handle(req())
    await drain()
    assert (await co.handle(req(job="job_two"))).state == AlertState.BUSY
    assert (await co.handle(req("STOP", source="b"))).state == AlertState.NOT_FOUND
    await co.event("b", "job_one", "COMPLETED")
    assert (await co.handle(req("STATUS"))).state == AlertState.ACCEPTED
    await co.wake("a")
    await co.event("a", "job_one", "PLAYING")
    assert (await co.handle(req("STATUS"))).state == AlertState.STOPPED
    await co.shutdown()


@pytest.mark.asyncio
async def test_restart_reconciles_firmware_and_never_replays_unknown():
    backend = Backend()
    disk = Disk()
    co = AlertCoordinator(backend, disk.save)
    await co.handle(req())
    await drain()
    backend.report["job_one"] = "PLAYING"
    restored = AlertCoordinator(backend, disk.save, records=disk.data)
    await restored.restore()
    assert (await restored.handle(req("STATUS"))).state == AlertState.PLAYING
    backend.report.clear()
    lost = AlertCoordinator(backend, disk.save, records=disk.data)
    await lost.restore()
    assert (await lost.handle(req("STATUS"))).state == AlertState.UNKNOWN_OUTCOME
    assert (await lost.handle(req())).state == AlertState.UNKNOWN_OUTCOME
    assert len(backend.commands) == 1
    await co.shutdown()
    await restored.shutdown()
    await lost.shutdown()


@pytest.mark.asyncio
async def test_backend_discovers_exact_source_and_sends_epoch_guarded_command():
    import json
    from types import SimpleNamespace
    from homeassistant.custom_components.nyra.alert_backend import (
        HomeAssistantAlertBackend,
    )
    from homeassistant.custom_components.nyra.esphome import SpeakerTarget

    calls = []
    states = {
        "text.a": SimpleNamespace(state=""),
        "sensor.epoch": SimpleNamespace(state="123"),
        "sensor.state": SimpleNamespace(state="job_one|PLAYING"),
    }

    class Services:
        async def async_call(self, domain, service, data, blocking):
            calls.append((domain, service, data, blocking))

    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=Services())
    target = SpeakerTarget(
        light_entity="light.a",
        alert_command_entity="text.a",
        audio_epoch_entity="sensor.epoch",
        alert_state_entity="sensor.state",
    )

    async def targets():
        return {"a": target}

    backend = HomeAssistantAlertBackend(hass, targets)
    assert await backend.available("a")
    assert not await backend.available("b")
    assert await backend.epoch("a") == "123"
    await backend.play(req(), "", "123")
    command = json.loads(calls[0][2]["value"])
    assert command == {
        "action": "START",
        "job_id": "job_one",
        "kind": "timer",
        "epoch": "123",
        "max_seconds": 60,
        "url": "",
    }
    assert calls[0][:2] == ("text", "set_value")
    assert calls[0][2]["entity_id"] == "text.a"
    assert await backend.status(req()) == "PLAYING"
    await backend.stop(req("STOP"))
    assert json.loads(calls[1][2]["value"])["action"] == "STOP"


@pytest.mark.asyncio
async def test_conversation_result_is_suppressed_if_alert_took_ownership():
    from homeassistant.custom_components.nyra.conversation import (
        AdapterInput,
        process_adapter_input,
    )
    from homeassistant.custom_components.nyra.session import SessionManager
    from shared.protocol.requests import (
        NyraRequestResponse,
        RequestStatus,
        NyraResponseBody,
    )

    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)

    class Client:
        async def async_execute(self, request):
            await co.handle(req())
            return NyraRequestResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                trace_id="trc_00000000-0000-0000-0000-000000000001",
                status=RequestStatus.COMPLETED,
                response=NyraResponseBody(text="late response"),
            )

    data = AdapterInput(
        text="ciao",
        language="it",
        conversation_key="a",
        satellite_id="assist_satellite.a",
        nyra_source_id="a",
    )
    result = await process_adapter_input(data, SessionManager(60), Client(), alerts=co)
    assert result.text == ""
    assert not result.continue_conversation
    await co.shutdown()


@pytest.mark.asyncio
async def test_remote_stop_waits_for_device_confirmation_and_survives_transport_error():
    class OfflineStop(Backend):
        async def stop(self, request):
            raise TimeoutError()

    backend = OfflineStop()
    disk = Disk()
    co = AlertCoordinator(backend, disk.save)
    await co.handle(req())
    await drain()
    result = await co.handle(req("STOP"))
    assert result.state != AlertState.STOPPED
    backend.report["job_one"] = "STOPPED"
    assert (await co.handle(req("STATUS"))).state == AlertState.STOPPED
    await co.shutdown()


@pytest.mark.asyncio
async def test_backend_chunks_long_tts_url_within_firmware_text_limit():
    import json
    from types import SimpleNamespace
    from homeassistant.custom_components.nyra.alert_backend import (
        HomeAssistantAlertBackend,
    )
    from homeassistant.custom_components.nyra.esphome import SpeakerTarget

    commands = []

    class Services:
        async def async_call(self, domain, service, data, blocking):
            commands.append(data["value"])

    states = {
        "text.a": SimpleNamespace(state=""),
        "sensor.epoch": SimpleNamespace(state="123"),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=Services())

    async def targets():
        return {
            "a": SpeakerTarget(
                light_entity="light.a",
                alert_command_entity="text.a",
                audio_epoch_entity="sensor.epoch",
            )
        }

    backend = HomeAssistantAlertBackend(hass, targets)
    url = "http://ha/tts/" + ("x" * 700) + ".mp3"
    await backend.play(req(), url, "123")
    assert all(len(command) <= 255 for command in commands)
    parts = [
        json.loads(c)["part"] for c in commands if json.loads(c)["action"] == "URL"
    ]
    assert "".join(parts) == url
    assert json.loads(commands[-1])["action"] == "START"


@pytest.mark.asyncio
async def test_router_failure_after_wake_cannot_trigger_fallback_speech():
    from homeassistant.custom_components.nyra.conversation import (
        AdapterInput,
        process_adapter_input,
        needs_home_assistant_fallback,
    )
    from homeassistant.custom_components.nyra.session import SessionManager
    from homeassistant.custom_components.nyra.client import NyraRouterError

    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)

    class Client:
        async def async_execute(self, request):
            await co.wake("a")
            raise NyraRouterError("offline")

    data = AdapterInput(
        text="ciao",
        language="it",
        conversation_key="a",
        satellite_id="assist_satellite.a",
        nyra_source_id="a",
    )
    result = await process_adapter_input(data, SessionManager(60), Client(), alerts=co)
    assert result.text == ""
    assert not needs_home_assistant_fallback(result)
    await co.shutdown()


@pytest.mark.asyncio
async def test_existing_notification_uses_alert_ownership_and_invalidates_conversation():
    from homeassistant.custom_components.nyra.esphome import EspHomeSpeakerOutput

    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)

    async def notify(source, message, language):
        return await co.handle(
            AlertRequest(
                action="START",
                job_id="job_notice",
                source_id=source,
                alert_kind="notification",
                message=message,
                language=language,
            )
        )

    async def forbidden(*args):
        raise AssertionError("notification bypassed audio ownership")

    output = EspHomeSpeakerOutput({}, forbidden, announcer=notify)
    before = co.generation("a")
    await output.announce("a", "Avviso di prova", language="it")
    await drain()
    assert co.generation("a") != before
    assert backend.commands == [("play", "job_notice", "a", "boot-1")]
    await co.wake("a")
    assert (
        await co.handle(req("STATUS", job="job_notice"))
    ).state == AlertState.STOPPED
    await co.shutdown()


@pytest.mark.asyncio
async def test_slow_device_command_does_not_block_another_source():
    gate = asyncio.Event()

    class SlowBackend(Backend):
        async def play(self, request, url, epoch):
            if request.source_id == "a":
                await gate.wait()
            await super().play(request, url, epoch)

    backend = SlowBackend()
    co = AlertCoordinator(backend, Disk().save)
    await co.handle(req())
    await drain()
    task = asyncio.create_task(co.handle(req(job="job_two", source="b")))
    await drain()
    assert task.done(), "another speaker was blocked behind a device command"
    assert task.result().state == AlertState.ACCEPTED
    gate.set()
    await drain()
    await co.shutdown()


@pytest.mark.asyncio
async def test_prepare_failure_is_failed_but_ambiguous_send_remains_reconcilable():
    class FailedPreparation(Backend):
        async def prepare(self, request):
            raise ValueError("TTS unavailable")

    first = AlertCoordinator(FailedPreparation(), Disk().save)
    await first.handle(req())
    await drain()
    assert (await first.handle(req("STATUS"))).state == AlertState.FAILED
    await first.shutdown()

    class TimeoutAfterSend(Backend):
        async def play(self, request, url, epoch):
            self.report[request.job_id] = "PLAYING"
            raise TimeoutError()

    backend = TimeoutAfterSend()
    second = AlertCoordinator(backend, Disk().save)
    await second.handle(req())
    await drain()
    assert (await second.handle(req("STATUS"))).state == AlertState.PLAYING
    assert (await second.handle(req(job="job_two"))).state == AlertState.BUSY
    await second.shutdown()


@pytest.mark.asyncio
async def test_delayed_wake_event_does_not_cancel_alert_started_in_new_epoch():
    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)
    await co.handle(req())
    await drain()
    # This event belongs to the wake that produced boot-1 before START accepted it.
    await co.wake("a", epoch="boot-1")
    assert (await co.handle(req("STATUS"))).state == AlertState.ACCEPTED
    await co.shutdown()


@pytest.mark.asyncio
async def test_command_missing_native_value_is_available_with_live_epoch():
    from types import SimpleNamespace
    from homeassistant.custom_components.nyra.alert_backend import (
        HomeAssistantAlertBackend,
    )
    from homeassistant.custom_components.nyra.esphome import SpeakerTarget

    states = {
        "text.a": SimpleNamespace(state="unknown"),
        "sensor.epoch": SimpleNamespace(state="123"),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))

    async def targets():
        return {
            "a": SpeakerTarget(
                light_entity="light.a",
                alert_command_entity="text.a",
                audio_epoch_entity="sensor.epoch",
            )
        }

    backend = HomeAssistantAlertBackend(hass, targets)
    assert await backend.available("a")
    states["text.a"].state = "unavailable"
    assert not await backend.available("a")


@pytest.mark.asyncio
async def test_lost_notification_terminal_event_is_reconciled_before_busy():
    backend = Backend()
    co = AlertCoordinator(backend, Disk().save)
    notice = AlertRequest(
        action="START",
        job_id="job_notice",
        source_id="a",
        alert_kind="notification",
        message="Avviso",
    )
    await co.handle(notice)
    await drain()
    backend.report["job_notice"] = "COMPLETED"
    assert (await co.handle(req())).state == AlertState.ACCEPTED
    await co.shutdown()


@pytest.mark.asyncio
async def test_stop_after_speaker_reboot_expires_using_stored_deadline(monkeypatch):
    import time

    class LostStop(Backend):
        async def stop(self, request):
            raise TimeoutError()

    backend = LostStop()
    co = AlertCoordinator(backend, Disk().save)
    await co.handle(req())
    await drain()
    accepted = co.records["job_one"]["accepted_at"]
    monkeypatch.setattr(time, "time", lambda: accepted + 3600)
    assert (await co.handle(req("STOP"))).state == AlertState.UNKNOWN_OUTCOME
    assert not co.active("a")
    assert (await co.handle(req(job="job_after"))).state == AlertState.ACCEPTED
    await co.shutdown()
