from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio
import pytest

from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import (
    RequestLifecycleService, LifecycleDecision, ContextResult, SkillMatch,
    LifecycleConflict,
)
from router.lifecycle.store import RequestStateStore
from shared.protocol.events import EventCategory, InteractionState
from shared.protocol.requests import CloseReason, NyraRequest, RequestStatus
from router.observability.ids import generate_request_id, generate_session_id


class Clock:
    def __init__(self): self.now = datetime(2026,8,30,20,0,tzinfo=timezone.utc)
    def __call__(self): return self.now


class IdentityPort:
    def __init__(self, detected="user-a"): self.detected=detected; self.calls=0
    async def identify(self, request, trace_id):
        self.calls += 1
        await asyncio.sleep(0)
        return self.detected


class ContextPort:
    def __init__(self, semantic=False): self.semantic=semantic; self.calls=[]
    async def resolve(self, request, identity_user_id):
        self.calls.append((request.input.text, identity_user_id))
        return ContextResult(data={"room":"living-room"}, semantic_memory_required=self.semantic)


class MemoryPort:
    def __init__(self): self.calls=0
    async def search(self, request, identity_user_id, context): self.calls += 1; return {"memory":"value"}


class SkillPort:
    def __init__(self, match=True, decision=None): self.match=match; self.decision=decision or LifecycleDecision.completed("Done."); self.checked=0; self.executed=0
    async def check(self, request, context, memory, pending_state): self.checked += 1; return SkillMatch(matched=self.match, token="skill-a" if self.match else None)
    async def execute(self, match, request, context, memory, pending_state): self.executed += 1; return self.decision


class LlmPort:
    def __init__(self, decision=None): self.calls=0; self.decision=decision or LifecycleDecision.completed("LLM done.")
    async def reason(self, request, context, memory, pending_state): self.calls += 1; return self.decision


def request(request_id=None, session_id=None, kind="ha_speaker", identity=None, text="turn on the light"):
    return NyraRequest.model_validate({
        "type":kind,
        "session_id":session_id or (None if kind=="job" else generate_session_id()),
        "request_id":request_id or (None if kind=="job" else generate_request_id()),
        "language":"it", "source":None if kind!="ha_speaker" else {"id":"speaker-a","area":"living-room"},
        "identity":identity, "input":{"text":text}
    })


def service(tmp_path, **overrides):
    store=RequestStateStore(tmp_path/"router.db"); store.initialize()
    broker=InteractionEventBroker()
    clock=overrides.pop("clock",Clock())
    deps=dict(store=store, broker=broker, clock=clock, identity_port=IdentityPort(), context_port=ContextPort(), memory_port=MemoryPort(), skill_port=SkillPort(), llm_port=LlmPort(), clarification_timeout_seconds=120)
    deps.update(overrides)
    return RequestLifecycleService(**deps), store, broker


@pytest.mark.asyncio
async def test_router_preserves_ingress_ids_creates_trace_and_persists_request(tmp_path):
    svc, store, _ = service(tmp_path)
    req=request()
    result=await svc.execute(req)
    assert result.session_id==req.session_id and result.request_id==req.request_id
    assert result.trace_id.startswith("trc_")
    assert store.get(req.request_id).current_trace_id==result.trace_id
    assert result.status is RequestStatus.COMPLETED


@pytest.mark.asyncio
async def test_job_has_trace_but_no_request_state(tmp_path):
    svc, store, _ = service(tmp_path)
    result=await svc.execute(request(kind="job"))
    assert result.session_id is None and result.request_id is None and result.trace_id.startswith("trc_")


@pytest.mark.asyncio
async def test_clarification_reuses_request_but_creates_new_trace(tmp_path):
    clock=Clock(); skill=SkillPort(decision=LifecycleDecision.needs_clarification("Which light?", {"missing":"entity"}))
    svc, store, _=service(tmp_path, clock=clock, skill_port=skill)
    req=request(); first=await svc.execute(req)
    assert first.status is RequestStatus.NEEDS_CLARIFICATION
    state=store.get(req.request_id); assert state.pending_state=={"missing":"entity"}
    first_trace=first.trace_id
    skill.decision=LifecycleDecision.completed("Done.")
    clock.now += timedelta(seconds=10)
    follow=request(req.request_id, req.session_id, text="living room")
    second=await svc.execute(follow)
    assert second.trace_id != first_trace and second.request_id==req.request_id
    assert second.status is RequestStatus.COMPLETED


@pytest.mark.asyncio
async def test_clarification_rejects_mismatched_session_and_expired_request(tmp_path):
    clock=Clock(); skill=SkillPort(decision=LifecycleDecision.needs_clarification("Which light?", {"missing":"entity"}))
    svc, store, _=service(tmp_path, clock=clock, skill_port=skill)
    req=request(); await svc.execute(req)
    with pytest.raises(LifecycleConflict):
        await svc.execute(request(req.request_id, generate_session_id(), text="living room"))
    clock.now += timedelta(seconds=121)
    expired=await svc.execute(request(req.request_id, req.session_id, text="living room"))
    assert expired.status is RequestStatus.EXPIRED


@pytest.mark.asyncio
async def test_closed_is_authoritative_persisted_and_publishes_session_closed(tmp_path):
    skill=SkillPort(decision=LifecycleDecision.closed(CloseReason.DIRECT_COMMAND, "Done."))
    svc, store, broker=service(tmp_path, skill_port=skill)
    sub=await broker.subscribe({EventCategory.SESSION})
    req=request(); result=await svc.execute(req)
    assert result.status is RequestStatus.CLOSED and result.close_reason is CloseReason.DIRECT_COMMAND
    assert store.get(req.request_id).status is RequestStatus.CLOSED
    event=await asyncio.wait_for(sub.queue.get(), .2)
    assert event.event=="SESSION_CLOSED" and event.close_reason is CloseReason.DIRECT_COMMAND
    with pytest.raises(LifecycleConflict): await svc.execute(request(req.request_id, req.session_id))


@pytest.mark.asyncio
async def test_alarm_dismissal_can_close_without_response_body(tmp_path):
    skill=SkillPort(decision=LifecycleDecision.closed(CloseReason.ALARM_DISMISSED, None))
    svc, _, _=service(tmp_path, skill_port=skill)
    result=await svc.execute(request())
    assert result.status is RequestStatus.CLOSED and result.response is None


@pytest.mark.asyncio
async def test_identity_semantics_and_trusted_ha_identity(tmp_path):
    identity=IdentityPort("user-a")
    svc, store, broker=service(tmp_path, identity_port=identity)
    sub=await broker.subscribe({EventCategory.INTERACTION_STATE})
    req=request(); await svc.execute(req)
    assert identity.calls==1 and store.get(req.request_id).identity_user_id=="user-a"
    states=[]
    while not sub.queue.empty(): states.append(sub.queue.get_nowait().state)
    assert InteractionState.IDENTIFYING in states

    trusted=IdentityPort("wrong")
    svc2, store2, _=service(tmp_path/"trusted", identity_port=trusted)
    req2=request(kind="ha_assist", identity={"user_id":"user-b","provider":"home_assistant","confidence":1.0})
    await svc2.execute(req2)
    assert trusted.calls==0 and store2.get(req2.request_id).identity_user_id=="user-b"


@pytest.mark.asyncio
async def test_memory_skill_and_llm_state_paths(tmp_path):
    context=ContextPort(semantic=True); memory=MemoryPort(); skill=SkillPort(match=False); llm=LlmPort()
    svc, _, broker=service(tmp_path, context_port=context, memory_port=memory, skill_port=skill, llm_port=llm)
    sub=await broker.subscribe({EventCategory.INTERACTION_STATE})
    result=await svc.execute(request(kind="ha_assist", identity={"user_id":"user-a","provider":"home_assistant","confidence":1.0}))
    assert result.response.text=="LLM done." and memory.calls==1 and skill.executed==0 and llm.calls==1
    states=[]
    while not sub.queue.empty(): states.append(sub.queue.get_nowait().state)
    for required in [InteractionState.PROCESSING, InteractionState.MEMORY, InteractionState.SKILL_CHECK, InteractionState.LLM_REASONING]:
        assert required in states


@pytest.mark.asyncio
async def test_semantic_memory_can_be_skipped_but_context_always_runs(tmp_path):
    context=ContextPort(semantic=False); memory=MemoryPort()
    svc, _, _=service(tmp_path, context_port=context, memory_port=memory)
    await svc.execute(request(kind="ha_assist", identity={"user_id":"user-a","provider":"home_assistant","confidence":1.0}))
    assert len(context.calls)==1 and memory.calls==0

class Collector:
    def __init__(self): self.records=[]
    def ingest(self, records): self.records.extend(records); return len(records)


@pytest.mark.asyncio
async def test_lifecycle_observability_pairs_request_and_response_and_logs_identity_and_close(tmp_path):
    collector=Collector(); skill=SkillPort(decision=LifecycleDecision.closed(CloseReason.DIRECT_COMMAND, "Done."))
    svc, _, _=service(tmp_path, observability=collector, skill_port=skill)
    await svc.execute(request())
    events=[r.event for r in collector.records]
    assert "REQUEST_RECEIVED" in events
    assert "REQUEST_COMPLETED" in events
    assert "IDENTITY_IDENTIFIED" in events
    assert "SESSION_CLOSED" in events
    request_record=next(r for r in collector.records if r.event=="REQUEST_RECEIVED")
    response_record=next(r for r in collector.records if r.event=="REQUEST_COMPLETED")
    assert request_record.span_id==response_record.span_id
    assert request_record.kind.value=="REQUEST" and response_record.kind.value=="RESPONSE"
    assert response_record.result=="closed"

@pytest.mark.asyncio
async def test_new_request_in_same_session_confirms_or_changes_previous_identity(tmp_path):
    collector=Collector(); identity=IdentityPort("user-a")
    svc, store, _=service(tmp_path, observability=collector, identity_port=identity)
    first=request(); await svc.execute(first)
    second=request(session_id=first.session_id); await svc.execute(second)
    assert any(r.event=="IDENTITY_CONFIRMED" for r in collector.records)
    identity.detected="user-b"
    third=request(session_id=first.session_id); await svc.execute(third)
    assert any(r.event=="IDENTITY_CHANGED" and r.params.get("current_user_id")=="user-b" for r in collector.records)
    identity.detected=None
    fourth=request(session_id=first.session_id); await svc.execute(fourth)
    assert any(r.event=="IDENTITY_GUEST" and r.params.get("current_user_id")=="guest" for r in collector.records)
