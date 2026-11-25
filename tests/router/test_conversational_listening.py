import pytest

from router.router_llm_port import RouterLlmPort
from router.lifecycle.service import ContextResult
from shared.protocol.llm import ReasoningResult, ReasoningOutcome
from shared.protocol.requests import RequestStatus, CloseReason
from tests.router.test_request_lifecycle import request, service, SkillPort
from router.lifecycle.service import SkillMatch
from shared.protocol.skills import SkillOutcome


class MissSkills(SkillPort):
    async def check(self, *args):
        return SkillMatch(matched=False, outcome=SkillOutcome.MISS)


class Model:
    def __init__(self):
        self.contexts = []
        self.llm_client = self

    async def semantic(self, request):
        from shared.protocol.semantic import SemanticResult
        return SemanticResult(intent="conversation")

    async def reason(self, **kwargs):
        self.contexts.append(kwargs)
        return ReasoningResult(outcome=ReasoningOutcome.COMPLETED, reasoning_id="r", response_text="Parliamo di libri.")


@pytest.mark.asyncio
async def test_plain_conversation_continues_and_persists_both_sides(tmp_path):
    model = Model()
    svc, store, _ = service(tmp_path, skill_port=MissSkills())
    svc.llm_port = RouterLlmPort(model, history_store=store)
    first = request(kind="ha_assist", text="Parliamo di libri")
    result = await svc.execute(first)
    assert result.continue_conversation is True
    second = request(kind="ha_assist", session_id=first.session_id, text="Mi piacciono i gialli")
    await svc.execute(second)
    assert model.contexts[-1]["conversation_history"] == [
        {"role": "user", "content": "Parliamo di libri"},
        {"role": "assistant", "content": "Parliamo di libri."},
    ]
    assert store.get(first.request_id).response_text == "Parliamo di libri."


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Grazie!", "chiudi", "OK grazie.", "ok", "Thank you!"])
async def test_exact_closing_phrase_never_reaches_skills_or_llm(tmp_path, text):
    skills = SkillPort()
    svc, store, _ = service(tmp_path, skill_port=skills)
    req = request(text=text)
    result = await svc.execute(req)
    assert result.status is RequestStatus.CLOSED
    assert result.close_reason is CloseReason.EXPLICIT_CLOSE
    assert not result.continue_conversation
    assert skills.checked == 0
    assert store.get(req.request_id).status is RequestStatus.CLOSED


@pytest.mark.asyncio
async def test_command_with_polite_prefix_is_executed_and_does_not_continue(tmp_path):
    skills = SkillPort()
    svc, _, _ = service(tmp_path, skill_port=skills)
    result = await svc.execute(request(text="ok accendi la luce grazie"))
    assert skills.executed == 1
    assert result.status is RequestStatus.COMPLETED
    assert not result.continue_conversation


@pytest.mark.asyncio
async def test_clarification_answer_remains_in_later_conversation_history(tmp_path):
    from shared.protocol.llm import ClarificationRequest

    class ClarifyingModel(Model):
        async def reason(self, **kwargs):
            self.contexts.append(kwargs)
            if len(self.contexts) == 1:
                return ReasoningResult(outcome=ReasoningOutcome.NEEDS_CLARIFICATION, reasoning_id="r", clarification=ClarificationRequest(question="Che genere preferisci?"))
            return ReasoningResult(outcome=ReasoningOutcome.COMPLETED, reasoning_id="r", response_text="Ti suggerisco un giallo.")

    model = ClarifyingModel()
    svc, store, _ = service(tmp_path, skill_port=MissSkills())
    svc.llm_port = RouterLlmPort(model, history_store=store)
    first = request(kind="ha_assist", text="Consigliami un libro")
    await svc.execute(first)
    await svc.execute(request(kind="ha_assist", request_id=first.request_id, session_id=first.session_id, text="Un giallo"))
    assert model.contexts[-1]["conversation_history"] == [
        {"role": "user", "content": "Consigliami un libro"},
        {"role": "assistant", "content": "Che genere preferisci?"},
    ]
    await svc.execute(request(kind="ha_assist", session_id=first.session_id, text="Un altro?"))
    assert model.contexts[-1]["conversation_history"] == [
        {"role": "user", "content": "Consigliami un libro"},
        {"role": "assistant", "content": "Che genere preferisci?"},
        {"role": "user", "content": "Un giallo"},
        {"role": "assistant", "content": "Ti suggerisco un giallo."},
    ]


@pytest.mark.asyncio
async def test_legacy_request_database_migrates_without_losing_old_requests(tmp_path):
    import sqlite3
    from router.lifecycle.store import RequestStateStore

    svc, store, _ = service(tmp_path)
    original = request(text="accendi la luce")
    await svc.execute(original)
    with sqlite3.connect(store.path) as connection:
        connection.execute("ALTER TABLE request_states DROP COLUMN response_text")
        connection.execute("ALTER TABLE request_states DROP COLUMN conversation_turns_json")
    restored = RequestStateStore(store.path)
    restored.initialize()
    restored.initialize()
    old = restored.get(original.request_id)
    assert old.original_input == "accendi la luce"
    assert old.response_text is None
    assert old.conversation_turns == []
    old.response_text = "Fatto"
    old.conversation_turns = [{"role": "assistant", "content": "Fatto"}]
    restored.update(old)
    assert restored.get(original.request_id).conversation_turns == [{"role": "assistant", "content": "Fatto"}]
