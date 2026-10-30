import pytest
from pydantic import ValidationError
from shared.protocol.semantic import SemanticResult
from router.semantic_skill_bridge import SemanticSkillBridge


def test_music_semantics_accepts_contextual_commands_without_generic_targets():
    result = SemanticResult.model_validate(
        {
            "intent": "MUSIC",
            "confidence": {"score": 0.95},
            "music": {
                "action": "PLAY",
                "query": "Queen",
                "media_type": "artist",
                "areas": [],
            },
        }
    )
    assert SemanticSkillBridge().accept(result) == result
    assert (
        SemanticSkillBridge().accept(result.model_copy(update={"confidence": None}))
        is None
    )


@pytest.mark.parametrize(
    "command",
    [
        {"action": "PLAY"},
        {"action": "VOLUME", "volume": 101},
        {"action": "PAUSE", "query": "Queen"},
        {"action": "PLAY", "query": "Queen", "entity_id": "media_player.other"},
        {"action": "PLAY", "query": "https://evil.test/song"},
    ],
)
def test_music_contract_rejects_invalid_or_untrusted_execution_fields(command):
    from shared.protocol.music import MusicCommand

    with pytest.raises(ValidationError):
        MusicCommand.model_validate(command)


def test_music_cannot_mix_generic_actions_or_temporal_behavior():
    result = SemanticResult.model_validate(
        {
            "intent": "MUSIC",
            "confidence": {"score": 1},
            "music": {"action": "PAUSE"},
            "actions": [
                {
                    "operation": "TURN_ON",
                    "target": {"reference": "Queen", "kind": "SCENE"},
                }
            ],
        }
    )
    assert SemanticSkillBridge().accept(result) is None


@pytest.mark.asyncio
async def test_music_skill_uses_semantic_metadata_and_source_not_llm_entity():
    from skills.modules.music import MusicSkill
    from shared.protocol.skills import SkillCheckRequest, SkillExecuteRequest

    calls = []

    class Capability:
        async def music(self, payload):
            calls.append(payload)
            return {"status": "OK", "text": "Riproduco Queen."}

    skill = MusicSkill(Capability())
    req = SkillCheckRequest(
        correlation={
            "request_id": "req_00000000-0000-4000-8000-000000000001",
            "origin_request_id": "req_00000000-0000-4000-8000-000000000001",
            "trace_id": "trc_00000000-0000-4000-8000-000000000002",
        },
        text="Fammi ascoltare qualcosa dei Queen",
        language="it",
        context={"source_id": "source1", "session_id": "ses_1"},
        semantic={
            "intent": "MUSIC",
            "confidence": {"score": 1},
            "music": {"action": "PLAY", "query": "Queen", "media_type": "artist"},
        },
    )
    assert skill.matches(req)
    response = await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=skill.match(req),
            text=req.text,
            language="it",
            context=req.context,
        )
    )
    assert response.text == "Riproduco Queen."
    assert calls[0]["source_id"] == "source1" and calls[0]["session_id"] == "ses_1"
    assert calls[0]["command"]["query"] == "Queen"


@pytest.mark.asyncio
async def test_music_clarification_selects_only_bound_opaque_choice():
    from skills.modules.music import MusicSkill
    from shared.protocol.skills import SkillExecuteRequest, SkillMatch

    calls = []

    class Capability:
        async def music(self, payload):
            calls.append(payload)
            return {"status": "OK", "text": "Fatto."}

    skill = MusicSkill(Capability())
    req = SkillExecuteRequest(
        correlation={
            "request_id": "req_00000000-0000-4000-8000-000000000001",
            "origin_request_id": "req_00000000-0000-4000-8000-000000000001",
            "trace_id": "trc_00000000-0000-4000-8000-000000000002",
        },
        match=SkillMatch(matched=True, skill_name="music"),
        text="la seconda",
        language="it",
        context={"source_id": "s", "session_id": "session"},
        pending_state={
            "kind": "music",
            "choices": [{"token": "one", "label": "A"}, {"token": "two", "label": "B"}],
        },
    )
    await skill.execute(req)
    assert calls[0]["selection"] == "two" and calls[0]["session_id"] == "session"


@pytest.mark.parametrize(
    "text",
    [
        "pausa",
        "riprendi",
        "che ore sono?",
        "ricordami una cosa",
        "turn off the light",
        "Mansarda",
    ],
)
def test_pending_room_does_not_swallow_new_commands_or_bypass_semantics(text):
    from skills.modules.music import MusicSkill
    from shared.protocol.skills import SkillCheckRequest

    request = SkillCheckRequest(
        correlation={
            "request_id": "req_00000000-0000-4000-8000-000000000001",
            "origin_request_id": "req_00000000-0000-4000-8000-000000000001",
            "trace_id": "trc_00000000-0000-4000-8000-000000000002",
        },
        text=text,
        language="it",
        pending_state={
            "kind": "music_room",
            "command": {"action": "PLAY", "query": "Queen"},
        },
    )
    assert not MusicSkill(None).matches(request)


@pytest.mark.asyncio
async def test_room_answer_expires_and_cannot_execute_old_catalog_command():
    from skills.modules.music import MusicSkill
    from shared.protocol.skills import SkillExecuteRequest, SkillMatch

    calls = []

    class Capability:
        async def music(self, payload):
            calls.append(payload)
            return {"status": "OK", "text": "Fatto."}

    skill = MusicSkill(Capability(), clock=lambda: 121)
    req = SkillExecuteRequest(
        correlation={
            "request_id": "req_00000000-0000-4000-8000-000000000001",
            "origin_request_id": "req_00000000-0000-4000-8000-000000000001",
            "trace_id": "trc_00000000-0000-4000-8000-000000000002",
        },
        match=SkillMatch(
            matched=True,
            skill_name="music",
            metadata={
                "command": {"action": "PLAY", "query": "Queen", "areas": ["Mansarda"]}
            },
        ),
        text="Mansarda",
        language="it",
        context={"source_id": "s", "session_id": "session"},
        pending_state={
            "kind": "music_room",
            "command": {"action": "PLAY", "query": "Queen"},
            "source_id": "s",
            "session_id": "session",
            "expires_at": 120,
        },
    )
    result = await skill.execute(req)
    assert not calls and "scadut" in result.text


def test_music_bridge_keeps_default_source_and_rejects_discussion_as_playback():
    result = SemanticResult.model_validate(
        {
            "intent": "MUSIC",
            "confidence": {"score": 1},
            "music": {"action": "PLAY", "query": "Queen", "areas": ["Soggiorno"]},
        }
    )
    bridge = SemanticSkillBridge()
    assert bridge.accept(result, text="Fammi ascoltare Queen").music.areas == []
    assert bridge.accept(result, text="Parliamo dei Queen") is None
    assert bridge.accept(result, text="Tell me about Queen") is None


def test_music_bridge_never_turns_additive_playback_into_transfer():
    result = SemanticResult.model_validate(
        {
            "intent": "MUSIC",
            "confidence": {"score": 1},
            "music": {"action": "TRANSFER", "areas": ["Mansarda"]},
        }
    )
    assert (
        SemanticSkillBridge()
        .accept(result, text="Mettila anche in mansarda")
        .music.action
        == "GROUP"
    )
