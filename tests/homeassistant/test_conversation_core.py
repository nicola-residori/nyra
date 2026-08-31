import pytest
from homeassistant.custom_components.nyra.conversation import AdapterInput, build_request, process_adapter_input
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
