import pytest
from shared.protocol.ids import new_request_id, new_trace_id


def request(command=None, **kwargs):
    from shared.protocol.music import MusicRequest

    rid = new_request_id()
    return MusicRequest(
        source_id="source1",
        session_id="session1",
        language="it",
        correlation={
            "request_id": rid,
            "origin_request_id": rid,
            "trace_id": new_trace_id(),
        },
        command=command,
        **kwargs,
    )


class Backend:
    def __init__(self):
        self.players = [
            {
                "source_id": "source1",
                "area": "Soggiorno",
                "entity_id": "media_player.ma_one",
                "config_entry_id": "ma",
                "alert_state": "none|IDLE",
            },
            {
                "source_id": "source2",
                "area": "Mansarda",
                "entity_id": "media_player.ma_two",
                "config_entry_id": "ma",
                "alert_state": "none|IDLE",
            },
        ]
        self.items = [
            {
                "uri": "apple_music://track/one",
                "name": "One",
                "media_type": "track",
                "provider": "apple_music",
                "artists": [{"name": "Artist"}],
            }
        ]
        self.calls = []
        self.current = {
            "state": "playing",
            "active_queue": "queue1",
            "source": "Music Assistant",
        }

    async def inventory(self):
        return self.players

    async def search(self, player, query, media_type):
        return self.items

    async def play(self, player, item):
        self.calls.append(("play", player["entity_id"], item["uri"]))

    async def state(self, player):
        return self.current

    async def control(self, player, command):
        self.calls.append((command.action, player["entity_id"], command.volume))

    async def transfer(self, source, target):
        self.calls.append(("transfer", source["entity_id"], target["entity_id"]))


@pytest.mark.asyncio
async def test_default_source_explicit_area_and_no_fallback():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    b = Backend()
    c = MusicCoordinator(b)
    assert (await c.handle(request({"action": "PLAY", "query": "One"})))[
        "status"
    ] == "OK"
    assert b.calls[-1][1] == "media_player.ma_one"
    await c.handle(request({"action": "PLAY", "query": "One", "areas": ["mansarda"]}))
    assert b.calls[-1][1] == "media_player.ma_two"
    before = len(b.calls)
    assert (
        await c.handle(request({"action": "PLAY", "query": "One", "areas": ["studio"]}))
    )["status"] == "CLARIFY"
    b.players.append(dict(b.players[0]))
    assert (await c.handle(request({"action": "PAUSE"})))["status"] == "ERROR"
    assert len(b.calls) == before


@pytest.mark.asyncio
async def test_catalog_choice_bound_expiring_single_use_and_revalidated():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    b = Backend()
    b.items *= 2
    b.items[1] = dict(b.items[1], uri="apple_music://track/two", name="Two")
    now = [0]
    c = MusicCoordinator(b, clock=lambda: now[0])
    result = await c.handle(request({"action": "PLAY", "query": "name"}))
    assert result["status"] == "CLARIFY" and not b.calls
    token = result["choices"][1]["token"]
    wrong = request(selection=token).model_copy(update={"source_id": "source2"})
    assert (await c.handle(wrong))["status"] == "ERROR" and not b.calls
    assert (await c.handle(request(selection=token)))["status"] == "OK"
    assert b.calls[-1][2] == "apple_music://track/two"
    assert (await c.handle(request(selection=token)))["status"] == "ERROR"
    result = await c.handle(request({"action": "PLAY", "query": "name"}))
    now[0] = 121
    assert (await c.handle(request(selection=result["choices"][0]["token"])))[
        "status"
    ] == "ERROR"
    now[0] = 200
    result = await c.handle(request({"action": "PLAY", "query": "name"}))
    b.items = []
    assert (await c.handle(request(selection=result["choices"][0]["token"])))[
        "status"
    ] == "ERROR"


@pytest.mark.asyncio
async def test_contextual_controls_no_queue_intrusion_and_multiroom_are_truthful():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    b = Backend()
    c = MusicCoordinator(b)
    await c.handle(request({"action": "PAUSE"}))
    assert b.calls[-1][0] == "PAUSE"
    await c.handle(request({"action": "TRANSFER", "areas": ["Mansarda"]}))
    assert b.calls[-1] == ("transfer", "media_player.ma_one", "media_player.ma_two")
    before = len(b.calls)
    b.current = {"state": "idle", "active_queue": None}
    assert (await c.handle(request({"action": "NEXT"})))["status"] == "ERROR"
    b.current = {"state": "playing", "active_queue": None, "source": "AirPlay"}
    assert (await c.handle(request({"action": "NEXT"})))["status"] == "ERROR"
    b.players[0]["alert_state"] = "intrusion:18|PLAYING"
    assert (await c.handle(request({"action": "PLAY", "query": "One"})))[
        "status"
    ] == "ERROR"
    assert (await c.handle(request({"action": "GROUP", "areas": ["Mansarda"]})))[
        "status"
    ] == "ERROR"
    assert len(b.calls) == before


def test_registry_join_uses_stable_source_and_ma_unique_id_not_display_names():
    from homeassistant.custom_components.nyra.music import discover_music_players

    entities = [
        {
            "entity_id": "sensor.source",
            "platform": "esphome",
            "device_id": "d1",
            "original_name": "Nyra Source ID",
        },
        {
            "entity_id": "media_player.physical",
            "platform": "esphome",
            "device_id": "d1",
        },
        {
            "entity_id": "media_player.renamed",
            "platform": "music_assistant",
            "unique_id": "media_player.physical",
            "config_entry_id": "entry",
        },
    ]
    devices = [{"id": "d1", "area_id": "area1"}]
    areas = [{"id": "area1", "name": "Soggiorno"}]
    result = discover_music_players(
        devices, entities, {"sensor.source": "source1"}, areas
    )
    assert (
        result[0]["entity_id"] == "media_player.renamed"
        and result[0]["source_id"] == "source1"
    )
    entities.append(dict(entities[-1], entity_id="media_player.duplicate"))
    with pytest.raises(ValueError):
        discover_music_players(devices, entities, {"sensor.source": "source1"}, areas)


@pytest.mark.asyncio
async def test_retry_does_not_repeat_next_or_restart_playback():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    b = Backend()
    c = MusicCoordinator(b)
    r = request({"action": "NEXT"})
    assert (await c.handle(r))["status"] == "OK"
    assert (await c.handle(r))["status"] == "OK"
    assert len(b.calls) == 1


@pytest.mark.asyncio
async def test_unknown_room_asks_and_retains_original_catalog_request():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    c = MusicCoordinator(Backend())
    result = await c.handle(
        request(
            {
                "action": "PLAY",
                "query": "Queen",
                "media_type": "artist",
                "areas": ["studio"],
            }
        )
    )
    assert result["status"] == "CLARIFY" and result["pending"]["kind"] == "music_room"
    assert result["pending"]["command"]["query"] == "Queen"


def test_music_view_is_owned_by_runtime_for_disable_on_unload():
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "homeassistant/custom_components/nyra/__init__.py"
    )
    calls = [
        n
        for n in ast.walk(ast.parse(source.read_text()))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "NyraRuntime"
    ]
    assert any(k.arg == "music_view" for call in calls for k in call.keywords)


@pytest.mark.asyncio
async def test_native_ha_search_contract_uses_flat_limit_and_filters_apple():
    from types import SimpleNamespace
    from homeassistant.custom_components.nyra.music import HomeAssistantMusicBackend

    class Services:
        async def async_call(self, domain, service, data, **kwargs):
            assert domain == "music_assistant" and service == "search"
            assert data["limit"] == 5 and "search_options" not in data
            assert kwargs == {"blocking": True, "return_response": True}
            return {
                "artists": [
                    {
                        "name": "Queen",
                        "uri": "apple_music://artist/queen",
                        "provider": "apple_music",
                    },
                    {
                        "name": "Queen",
                        "uri": "other://artist/queen",
                        "provider": "other",
                    },
                ]
            }

    results = await HomeAssistantMusicBackend(
        SimpleNamespace(services=Services())
    ).search({"config_entry_id": "ma"}, "Queen", "artist")
    assert len(results) == 1 and results[0]["media_type"] == "artist"


@pytest.mark.asyncio
async def test_clarification_reuses_router_request_id_without_replaying_side_effect():
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    b = Backend()
    b.items.append(dict(b.items[0], uri="apple_music://track/two", name="Two"))
    c = MusicCoordinator(b)
    initial = request({"action": "PLAY", "query": "name"})
    choices = (await c.handle(initial))["choices"]
    selected = request(selection=choices[1]["token"]).model_copy(
        update={"correlation": initial.correlation}
    )
    assert (await c.handle(selected))["status"] == "OK"
    assert (await c.handle(selected))["status"] == "OK"
    assert len(b.calls) == 1 and b.calls[0][2] == "apple_music://track/two"


@pytest.mark.asyncio
async def test_slow_catalog_search_is_cancelled_without_late_playback():
    import asyncio
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    class SlowBackend(Backend):
        async def search(self, *args):
            await asyncio.sleep(1)
            return self.items

    b = SlowBackend()
    c = MusicCoordinator(b, timeout_seconds=0.01)
    assert (await c.handle(request({"action": "PLAY", "query": "One"})))[
        "status"
    ] == "ERROR"
    await asyncio.sleep(0.02)
    assert not b.calls


@pytest.mark.asyncio
async def test_mutation_ack_delay_is_pending_not_false_failure_or_duplicate_play():
    import asyncio
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    class AcceptedBackend(Backend):
        async def play(self, player, item):
            self.calls.append(("accepted", item["uri"]))
            await asyncio.sleep(0.02)
            return False

    b = AcceptedBackend()
    c = MusicCoordinator(b, timeout_seconds=0.01)
    r = request({"action": "PLAY", "query": "One"})
    response = await c.handle(r)
    assert response["status"] == "PENDING" and "prepar" in response["text"]
    assert (await c.handle(r)) == response and len(b.calls) == 1


@pytest.mark.asyncio
async def test_artist_top_tracks_are_prepared_readonly_before_queue_dispatch():
    from types import SimpleNamespace
    from homeassistant.custom_components.nyra.music import HomeAssistantMusicBackend

    class Client:
        async def send_command(self, command, **kwargs):
            assert command == "music/artists/top_tracks"
            assert kwargs == {
                "item_id": "queen",
                "provider_instance_id_or_domain": "apple_music",
            }
            return [
                {"uri": "apple_music://track/one"},
                {"uri": "apple_music://track/two"},
                {"uri": "untrusted://track/bad"},
            ]

    entry = SimpleNamespace(runtime_data=SimpleNamespace(mass=Client()))
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _: entry)
    )
    prepared = await HomeAssistantMusicBackend(hass).prepare(
        {"config_entry_id": "ma"},
        {"uri": "apple_music://artist/queen", "name": "Queen", "media_type": "artist"},
    )
    assert prepared["media_ids"] == [
        "apple_music://track/one",
        "apple_music://track/two",
    ]
    assert prepared["media_type"] == "track" and prepared["name"] == "Queen"


@pytest.mark.asyncio
async def test_service_ack_task_survives_pending_response_and_stop_reaches_physical_player():
    import asyncio
    from types import SimpleNamespace
    from shared.protocol.music import MusicCommand
    from homeassistant.custom_components.nyra.music import HomeAssistantMusicBackend

    calls = []

    class Services:
        async def async_call(self, domain, service, data, **kwargs):
            calls.append((service, data["entity_id"]))
            if service == "play_media":
                await asyncio.sleep(0.03)

    backend = HomeAssistantMusicBackend(
        SimpleNamespace(services=Services()), ack_timeout=0.005
    )
    player = {"entity_id": "media_player.ma", "physical_entity_id": "media_player.raw"}
    assert (
        await backend.play(
            player, {"uri": "apple_music://track/one", "media_type": "track"}
        )
        is False
    )
    await asyncio.sleep(0.04)
    assert not backend.pending
    await backend.control(player, MusicCommand(action="STOP"))
    assert calls[-2:] == [
        ("media_stop", "media_player.raw"),
        ("media_stop", "media_player.ma"),
    ]


@pytest.mark.asyncio
async def test_waiting_for_another_music_command_cannot_execute_after_its_deadline():
    import asyncio
    from homeassistant.custom_components.nyra.music import MusicCoordinator

    class BusyBackend(Backend):
        async def play(self, player, item):
            self.calls.append(("accepted", item["uri"]))
            await asyncio.sleep(0.04)
            return False

    b = BusyBackend()
    c = MusicCoordinator(b, timeout_seconds=0.01)
    first = asyncio.create_task(c.handle(request({"action": "PLAY", "query": "One"})))
    await asyncio.sleep(0.002)
    second = await c.handle(request({"action": "PLAY", "query": "One"}))
    assert second["status"] == "ERROR"
    await first
    assert len(b.calls) == 1
