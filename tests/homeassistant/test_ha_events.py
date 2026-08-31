import pytest
from homeassistant.custom_components.nyra.events import RouterEventClient
from homeassistant.custom_components.nyra.speaker import SpeakerStateMachine


class Output:
    def __init__(self): self.calls=[]
    def __getattr__(self,name):
        async def call(*args): self.calls.append((name,*args))
        return call

async def unused_connect(url,headers): raise AssertionError


@pytest.mark.asyncio
async def test_event_messages_dispatch_to_target_speaker():
    out=Output(); sm=SpeakerStateMachine(out)
    client=RouterEventClient("http://router:8090","secret",unused_connect,sm)
    await client.handle_message({"event":"INTERACTION_STATE_CHANGED","category":"interaction_state","state":"PROCESSING_LOCAL","source":{"id":"speaker-a"}})
    await client.handle_message({"event":"IDENTITY_FEEDBACK","category":"identity","feedback":"IDENTITY_CHANGED","source":{"id":"speaker-a"}})
    assert out.calls == [("comet_turquoise","speaker-a"),("blink_identity","speaker-a",__import__('shared.protocol.events',fromlist=['IdentityFeedback']).IdentityFeedback.IDENTITY_CHANGED,2)]
    assert client.headers == {"Authorization":"Bearer secret"}
