from __future__ import annotations

from dataclasses import dataclass


from typing import Any

from shared.protocol.requests import (
    ExecutionType,
    NyraRequest,
    NyraRequestResponse,
    RequestInput,
    RequestSource,
    RequestStatus,
    TrustedIdentity,
)

from .client import NyraRouterError
from .esphome import resolve_nyra_source_id
from .session import SessionManager




@dataclass(frozen=True)
class AdapterInput:
    text: str
    language: str
    conversation_key: str
    device_id: str | None = None
    satellite_id: str | None = None
    nyra_source_id: str | None = None
    area: str | None = None
    user_id: str | None = None

    @property
    def source_id(self) -> str:
        return self.nyra_source_id or self.satellite_id or self.device_id or "home_assistant"

    @property
    def is_speaker(self) -> bool:
        return self.satellite_id is not None


@dataclass(frozen=True)
class AdapterResult:
    text: str
    conversation_key: str
    continue_conversation: bool
    response: NyraRequestResponse | None = None


def build_request(data: AdapterInput, sessions: SessionManager) -> NyraRequest:
    execution_type = ExecutionType.HA_SPEAKER if data.is_speaker else ExecutionType.HA_ASSIST
    identity = None
    if execution_type is ExecutionType.HA_ASSIST and data.user_id:
        identity = TrustedIdentity(user_id=data.user_id, provider="home_assistant", confidence=1.0)
    return NyraRequest(
        type=execution_type,
        session_id=sessions.get_or_create_session(data.conversation_key),
        request_id=sessions.get_request_id(data.conversation_key),
        language=data.language,
        source=RequestSource(id=data.source_id, area=data.area),
        identity=identity,
        input=RequestInput(text=data.text),
    )


async def process_adapter_input(data: AdapterInput, sessions: SessionManager, client) -> AdapterResult:
    request = build_request(data, sessions)
    try:
        response = await client.async_execute(request)
    except NyraRouterError:
        sessions.complete_request(data.conversation_key)
        return AdapterResult("Nyra non è disponibile in questo momento.", data.conversation_key, False)

    continuing = response.status is RequestStatus.NEEDS_CLARIFICATION
    if continuing:
        sessions.preserve_request(data.conversation_key)
    else:
        sessions.complete_request(data.conversation_key)
        if response.status is RequestStatus.CLOSED:
            sessions.close_session(data.conversation_key)

    text = response.response.text if response.response is not None else ""
    if response.status in {RequestStatus.FAILED, RequestStatus.EXPIRED} and not text:
        text = "Nyra non è riuscita a completare la richiesta."
    return AdapterResult(text, data.conversation_key, continuing, response)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up the Home Assistant conversation platform."""

    from homeassistant.components import conversation
    from homeassistant.const import MATCH_ALL
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import intent

    runtime = config_entry.runtime_data

    class NyraConversationEntity(conversation.ConversationEntity, conversation.AbstractConversationAgent):
        _attr_name = "Nyra"
        _attr_unique_id = config_entry.entry_id

        @property
        def supported_languages(self):
            return MATCH_ALL

        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()
            conversation.async_set_agent(self.hass, config_entry, self)

        async def async_will_remove_from_hass(self) -> None:
            conversation.async_unset_agent(self.hass, config_entry)
            await super().async_will_remove_from_hass()

        async def _async_handle_message(self, user_input, chat_log):
            conversation_key = user_input.conversation_id or f"ha:{user_input.context.id}"

            nyra_source_id = None
            if user_input.satellite_id:
                registry = er.async_get(self.hass)
                entities = list(registry.entities.values())
                source_entity_ids = {
                    entity.entity_id
                    for entity in entities
                    if entity.platform == "esphome"
                    and entity.original_name == "Nyra Source ID"
                }
                states = {
                    entity_id: self.hass.states.get(entity_id).state
                    for entity_id in source_entity_ids
                    if self.hass.states.get(entity_id) is not None
                }

                nyra_source_id = resolve_nyra_source_id(
                    user_input.satellite_id,
                    entities,
                    states,
                )


            data = AdapterInput(
                text=user_input.text,
                language=user_input.language,
                conversation_key=conversation_key,
                device_id=user_input.device_id,
                satellite_id=user_input.satellite_id,
                nyra_source_id=nyra_source_id,
                user_id=user_input.context.user_id,
            )
            result = await process_adapter_input(data, runtime.sessions, runtime.client)
            response = intent.IntentResponse(language=user_input.language)
            response.async_set_speech(result.text)
            return conversation.ConversationResult(
                response=response,
                conversation_id=result.conversation_key,
                continue_conversation=result.continue_conversation,
            )

    async_add_entities([NyraConversationEntity()])
