import httpx
import pytest
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import SkillExecuteRequest
from router.skills_client import SkillsClient


@pytest.mark.asyncio
@pytest.mark.parametrize("skill_name,expected", [("music", 18), ("identity", 3)])
async def test_music_execution_has_time_for_catalog_search_without_extending_other_skills(
    skill_name, expected
):
    rid = new_request_id()
    request = SkillExecuteRequest(
        correlation={
            "request_id": rid,
            "origin_request_id": rid,
            "trace_id": new_trace_id(),
        },
        match={"matched": True, "skill_name": skill_name},
        text="fammi ascoltare Queen",
        language="it",
    )

    def handle(r):
        assert r.extensions["timeout"]["read"] == expected
        return httpx.Response(
            200,
            json={
                "correlation": request.correlation.model_dump(mode="json"),
                "outcome": "HANDLED",
                "text": "Fatto.",
            },
        )

    assert (
        await SkillsClient(
            "http://skills", transport=httpx.MockTransport(handle)
        ).execute(request)
    ).text == "Fatto."
