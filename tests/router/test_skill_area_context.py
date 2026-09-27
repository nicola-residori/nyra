from __future__ import annotations

import pytest

from router.app import _RemoteSkillPort
from router.lifecycle.service import ContextResult
from shared.protocol.ids import new_request_id, new_session_id, new_trace_id
from shared.protocol.requests import ExecutionType, NyraRequest, RequestInput, RequestSource
from shared.protocol.skills import SkillCheckResponse, SkillOutcome


class Client:
    def __init__(self):
        self.payload = None

    async def check(self, payload):
        self.payload = payload
        return SkillCheckResponse(
            correlation=payload.correlation,
            outcome=SkillOutcome.MISS,
        )


@pytest.mark.asyncio
async def test_remote_skill_port_injects_trusted_request_area_into_skill_context():
    client = Client()
    port = _RemoteSkillPort(client)
    request = NyraRequest(
        type=ExecutionType.HA_SPEAKER,
        session_id=new_session_id(),
        request_id=new_request_id(),
        language="it",
        source=RequestSource(id="speaker-cucina", area="cucina"),
        input=RequestInput(text="accendi la luce"),
    )

    await port.check(
        request,
        ContextResult(data={}, trace_id=new_trace_id()),
        None,
        None,
    )

    assert client.payload.context["area"] == "cucina"
    assert client.payload.context["source_id"] == "speaker-cucina"
