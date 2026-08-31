import pytest

from homeassistant.custom_components.nyra.conversation import AdapterInput, build_request, process_adapter_input
from homeassistant.custom_components.nyra.esphome import resolve_nyra_source_id
from homeassistant.custom_components.nyra.session import SessionManager

from shared.protocol.ids import new_trace_id
from shared.protocol.requests import ExecutionType, NyraRequestResponse, NyraResponseBody, RequestStatus


class Client:

    def __init__(self,status): self.status=status; self.requests=[]

    async def async_execute(self,request):

        self.requests.append(request)

        return NyraRequestResponse(status=self.status,session_id=request.session_id,request_id=request.request_id,trace_id=new_trace_id(),response=NyraResponseBody(text="ok"))


def test_assist_identity_is_trusted_but_speaker_never_invents_identity():

    sessions=SessionManager()

    assist=build_request(AdapterInput("ciao","it","a",device_id="phone",user_id="user-a"),sessions)

    speaker=build_request(AdapterInput("ciao","it","b",satellite_id="nyra-soggiorno",user_id="user-a"),sessions)

    assert assist.type is ExecutionType.HA_ASSIST and assist.identity.user_id == "user-a"

    assert speaker.type is ExecutionType.HA_SPEAKER and speaker.identity is None

    assert speaker.source.id == "nyra-soggiorno"


def test_speaker_request_prefers_stable_nyra_source_id_over_ha_satellite_entity_id():

    sessions = SessionManager()

    speaker = build_request(
        AdapterInput(
            "ciao",
            "it-IT",
            "speaker-session",
            satellite_id="assist_satellite.renamed_voice_assistant",
            nyra_source_id="nyra-bedroom",
        ),
        sessions,
    )

    assert speaker.type is ExecutionType.HA_SPEAKER

    assert speaker.source.id == "nyra-bedroom"


def test_resolve_nyra_source_id_joins_satellite_to_source_sensor_on_same_device():

    entities = [
        {
            "entity_id": "assist_satellite.user_renamed_satellite",
            "device_id": "device-a",
            "platform": "esphome",
            "original_name": "Assist satellite",
        },
        {
            "entity_id": "sensor.user_renamed_source_id",
            "device_id": "device-a",
            "platform": "esphome",
            "original_name": "Nyra Source ID",
        },
        {
            "entity_id": "sensor.other_source_id",
            "device_id": "device-b",
            "platform": "esphome",
            "original_name": "Nyra Source ID",
        },
    ]
    states = {
        "sensor.user_renamed_source_id": "nyra-bedroom",
        "sensor.other_source_id": "nyra-kitchen",
    }

    assert resolve_nyra_source_id(
        "assist_satellite.user_renamed_satellite",
        entities,
        states,
    ) == "nyra-bedroom"


def test_resolve_nyra_source_id_returns_none_when_satellite_has_no_source_contract():

    entities = [
        {
            "entity_id": "assist_satellite.voice_assistant",
            "device_id": "device-a",
            "platform": "esphome",
            "original_name": "Assist satellite",
        }
    ]

    assert resolve_nyra_source_id(
        "assist_satellite.voice_assistant",
        entities,
        {},
    ) is None


@pytest.mark.asyncio

async def test_clarification_preserves_request_terminal_clears_it():

    sessions=SessionManager(); data=AdapterInput("luce","it","c")

    clar=Client(RequestStatus.NEEDS_CLARIFICATION)

    first=await process_adapter_input(data,sessions,clar)

    req_id=clar.requests[0].request_id

    assert first.continue_conversation

    done=Client(RequestStatus.COMPLETED)

    second=await process_adapter_input(data,sessions,done)

    assert done.requests[0].request_id == req_id

    await process_adapter_input(data,sessions,done)

    assert done.requests[1].request_id != req_id
