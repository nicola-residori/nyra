"""Trusted source-to-player resolution and MA catalog/queue execution."""

import asyncio
import json
import secrets
import time
from collections.abc import Mapping


def value(item, key, default=None):
    return (
        item.get(key, default)
        if isinstance(item, Mapping)
        else getattr(item, key, default)
    )


def discover_music_players(devices, entities, states, areas):
    devices = {value(d, "id"): d for d in devices}
    areas = {value(a, "id"): value(a, "name") for a in areas}
    entities = list(entities)
    result = []
    seen = set()
    for source in entities:
        if (
            value(source, "platform") != "esphome"
            or value(source, "original_name") != "Nyra Source ID"
        ):
            continue
        source_id = states.get(value(source, "entity_id"))
        if not source_id or source_id in ("unknown", "unavailable"):
            continue
        if source_id in seen:
            raise ValueError("duplicate source")
        seen.add(source_id)
        device_id = value(source, "device_id")
        physical = [
            e
            for e in entities
            if value(e, "device_id") == device_id
            and value(e, "platform") == "esphome"
            and value(e, "entity_id", "").startswith("media_player.")
            and not value(e, "disabled_by")
        ]
        if len(physical) != 1:
            continue
        physical = physical[0]
        players = [
            e
            for e in entities
            if value(e, "platform") == "music_assistant"
            and value(e, "unique_id") == value(physical, "entity_id")
            and value(e, "entity_id", "").startswith("media_player.")
            and not value(e, "disabled_by")
        ]
        if len(players) > 1:
            raise ValueError("ambiguous music player")
        if not players:
            continue
        player = players[0]
        area_id = value(physical, "area_id") or value(
            devices.get(device_id, {}), "area_id"
        )
        alert = next(
            (
                value(e, "entity_id")
                for e in entities
                if value(e, "device_id") == device_id
                and value(e, "original_name") == "Nyra Alert State"
            ),
            None,
        )
        result.append(
            {
                "source_id": source_id,
                "area": areas.get(area_id),
                "entity_id": value(player, "entity_id"),
                "physical_entity_id": value(physical, "entity_id"),
                "config_entry_id": value(player, "config_entry_id"),
                "alert_state": states.get(alert, "unknown"),
            }
        )
    return result


class MusicCoordinator:
    def __init__(self, backend, *, clock=time.monotonic):
        self.backend = backend
        self.clock = clock
        self.choices = {}
        self.results = {}
        self.lock = asyncio.Lock()

    async def handle(self, request):
        async with self.lock:
            self.choices = {
                k: v
                for k, v in self.choices.items()
                if self.clock() - v["created"] <= 120
            }
            fingerprint = request.model_dump(mode="json", exclude={"correlation"})
            key = (
                request.correlation.request_id,
                json.dumps(fingerprint, sort_keys=True),
            )
            self.results = {
                k: v for k, v in self.results.items() if self.clock() - v[0] <= 120
            }
            cached = self.results.get(key)
            if cached:
                if cached[1] != fingerprint:
                    return self.error(
                        request,
                        "La richiesta musicale è cambiata: ripetila.",
                        "The music request changed; repeat it.",
                    )
                return cached[2]
            try:
                result = await self._handle(request)
            except Exception:
                return self.error(
                    request,
                    "Il servizio musicale non è disponibile.",
                    "The music service is unavailable.",
                )
            if result["status"] in ("OK", "CLARIFY"):
                if len(self.results) >= 512:
                    self.results.pop(next(iter(self.results)))
                self.results[key] = (self.clock(), fingerprint, result)
            return result

    @staticmethod
    def error(request, it, en):
        return {
            "status": "ERROR",
            "text": it if request.language.startswith("it") else en,
        }

    async def _handle(self, r):
        players = await self.backend.inventory()
        source = [p for p in players if p["source_id"] == r.source_id]
        if len(source) != 1:
            return self.error(
                r,
                "Non trovo uno speaker musicale univoco per questa richiesta.",
                "I cannot find a unique music player for this speaker.",
            )
        origin = source[0]
        command = r.command
        selection = None
        if r.selection:
            selection = self.choices.get(r.selection)
            if not selection or (selection["source"], selection["session"]) != (
                r.source_id,
                r.session_id,
            ):
                return self.error(
                    r,
                    "La scelta non è più valida: ripeti la ricerca musicale.",
                    "That choice is no longer valid; repeat the music search.",
                )
            command = selection["command"]
        targets = []
        for area in command.areas:
            found = [
                p
                for p in players
                if (p.get("area") or "").casefold() == area.casefold()
            ]
            if len(found) != 1:
                return {
                    "status": "CLARIFY",
                    "text": (
                        "Quale stanza intendi?"
                        if r.language.startswith("it")
                        else "Which room do you mean?"
                    ),
                    "pending": {
                        "kind": "music_room",
                        "command": command.model_dump(mode="json"),
                        "source_id": r.source_id,
                        "session_id": r.session_id,
                        "expires_at": time.time() + 120,
                    },
                }
            if found[0] not in targets:
                targets.append(found[0])
        targets = targets or [origin]
        if len(targets) > 1 or command.action == "GROUP":
            return self.error(
                r,
                "La riproduzione sincronizzata su questi speaker non è ancora configurata.",
                "Synchronized playback on these speakers is not configured yet.",
            )
        player = targets[0]
        if any(
            p.get("alert_state", "").startswith("intrusion:")
            and p["alert_state"].endswith(("|ACCEPTED", "|PLAYING"))
            for p in (origin, player)
        ):
            return self.error(
                r,
                "La sirena antifurto ha la priorità sulla musica.",
                "The intrusion siren has priority over music.",
            )
        state = await self.backend.state(player)
        if state.get("state") in ("unavailable", "unknown"):
            return self.error(
                r,
                "Lo speaker musicale non è disponibile.",
                "The music speaker is unavailable.",
            )
        if command.action == "PLAY":
            items = await self.backend.search(player, command.query, command.media_type)
            unique = {item["uri"]: item for item in items if item.get("uri")}
            items = list(unique.values())[:3]
            if selection:
                self.choices.pop(r.selection, None)
                item = unique.get(selection["uri"])
                if not item or player["entity_id"] != selection["player"]:
                    return self.error(
                        r,
                        "Il risultato è cambiato: ripeti la ricerca.",
                        "The result changed; repeat the search.",
                    )
            elif len(items) == 1:
                item = items[0]
            elif items:
                if len(self.choices) > 509:
                    self.choices.clear()
                choices = []
                for item in items:
                    token = secrets.token_urlsafe(24)
                    self.choices[token] = {
                        "created": self.clock(),
                        "source": r.source_id,
                        "session": r.session_id,
                        "command": command,
                        "uri": item["uri"],
                        "player": player["entity_id"],
                    }
                    artists = ", ".join(
                        a.get("name", "") for a in item.get("artists", [])
                    )
                    label = " — ".join(
                        filter(
                            None, [item.get("name"), artists, item.get("media_type")]
                        )
                    )
                    choices.append({"token": token, "label": label})
                labels = "; ".join(
                    f'{i+1}: {c["label"]}' for i, c in enumerate(choices)
                )
                return {
                    "status": "CLARIFY",
                    "text": (
                        "Quale vuoi ascoltare? "
                        if r.language.startswith("it")
                        else "Which would you like? "
                    )
                    + labels,
                    "choices": choices,
                }
            else:
                return self.error(
                    r,
                    "Non trovo risultati su Apple Music. Se non è collegato, autorizza prima il tuo account in Music Assistant.",
                    "No Apple Music results. If disconnected, authorize your account in Music Assistant first.",
                )
            await self.backend.play(player, item)
            return {
                "status": "OK",
                "text": ("Riproduco " if r.language.startswith("it") else "Playing ")
                + item.get("name", command.query)
                + ".",
            }
        if command.action == "TRANSFER":
            current = await self.backend.state(origin)
            if not current.get("active_queue") or current.get("state") not in (
                "playing",
                "paused",
            ):
                return self.error(
                    r,
                    "Non c’è una coda musicale da trasferire su questo speaker.",
                    "There is no music queue to transfer from this speaker.",
                )
            await self.backend.transfer(origin, player)
        else:
            if command.action in ("NEXT", "PREVIOUS") and not state.get("active_queue"):
                return self.error(
                    r,
                    "Questa sorgente non offre una coda controllabile: cambia brano dal telefono.",
                    "This source has no controllable queue; change tracks on the phone.",
                )
            if (
                command.action in ("RESUME", "PAUSE", "STOP")
                and state.get("state") not in ("playing", "paused")
                and not state.get("active_queue")
            ):
                return self.error(
                    r,
                    "Non c’è una riproduzione musicale da controllare qui.",
                    "There is no music playback to control here.",
                )
            await self.backend.control(player, command)
        return {
            "status": "OK",
            "text": "Fatto." if r.language.startswith("it") else "Done.",
        }


class HomeAssistantMusicBackend:
    def __init__(self, hass):
        self.hass = hass

    async def inventory(self):
        from homeassistant.helpers import (
            device_registry as dr,
            entity_registry as er,
            area_registry as ar,
        )

        states = {s.entity_id: s.state for s in self.hass.states.async_all()}
        return discover_music_players(
            dr.async_get(self.hass).devices.values(),
            er.async_get(self.hass).entities.values(),
            states,
            ar.async_get(self.hass).areas.values(),
        )

    async def state(self, player):
        s = self.hass.states.get(player["entity_id"])
        return {"state": s.state, **s.attributes} if s else {"state": "unavailable"}

    async def search(self, player, query, media_type):
        data = {"config_entry_id": player["config_entry_id"], "name": query, "limit": 5}
        if media_type:
            data["media_type"] = [media_type]
        result = await self.hass.services.async_call(
            "music_assistant", "search", data, blocking=True, return_response=True
        )
        items = []
        for kind, values in (result or {}).items():
            if not isinstance(values, list):
                continue
            for item in values:
                mappings = item.get("provider_mappings") or []
                apple = (
                    item.get("provider") == "apple_music"
                    or item.get("uri", "").startswith("apple_music://")
                    or any(m.get("provider_domain") == "apple_music" for m in mappings)
                )
                if apple and item.get("uri", "").split("://", 1)[0] in (
                    "apple_music",
                    "library",
                ):
                    items.append(
                        {
                            **item,
                            "media_type": item.get("media_type") or kind.rstrip("s"),
                        }
                    )
        return items

    async def play(self, player, item):
        await self.hass.services.async_call(
            "music_assistant",
            "play_media",
            {
                "entity_id": player["entity_id"],
                "media_id": item["uri"],
                "media_type": item["media_type"],
                "enqueue": "replace",
            },
            blocking=True,
        )

    async def control(self, player, command):
        services = {
            "PAUSE": "media_pause",
            "RESUME": "media_play",
            "STOP": "media_stop",
            "NEXT": "media_next_track",
            "PREVIOUS": "media_previous_track",
            "VOLUME_UP": "volume_up",
            "VOLUME_DOWN": "volume_down",
            "VOLUME": "volume_set",
        }
        data = {"entity_id": player["entity_id"]}
        if command.action == "VOLUME":
            data["volume_level"] = command.volume / 100
        await self.hass.services.async_call(
            "media_player", services[command.action], data, blocking=True
        )

    async def transfer(self, source, target):
        await self.hass.services.async_call(
            "music_assistant",
            "transfer_queue",
            {"entity_id": target["entity_id"], "source_player": source["entity_id"]},
            blocking=True,
        )
