from pathlib import Path
from types import SimpleNamespace
from router.reasoning_context import build_reasoning_context

def src(p): return Path(p).read_text()

def test_reasoning_context_accepts_and_bounds_router_owned_history():
    r=SimpleNamespace(language="it",input=SimpleNamespace(text="x"),source=None,request_id=None,origin_request_id=None)
    c=SimpleNamespace(data={},trace_id="x")
    h=[{"role":"user","content":str(i)} for i in range(10)]
    assert build_reasoning_context(r,c,conversation_history=h).conversation_history==h[-6:]

def test_global_before_semantic():
    s=src("router/lifecycle/service.py"); i=s.index("elif match.outcome is SkillOutcome.MISS:")
    assert s.index("InteractionState.PROCESSING_GLOBAL",i)<s.index("self.llm_port.semantic",i)

def test_semantic_provider_observability():
    s=src("router/router_llm_port.py"); b=s[s.index("async def semantic"):s.index("async def reason")]
    assert "LLM_PROVIDER_REQUEST" in b and "LLM_PROVIDER_RESPONSE" in b and '"purpose":"SEMANTIC"' in b

def test_unavailable_distinct_from_rejected():
    p=src("router/router_llm_port.py"); l=src("router/lifecycle/service.py"); b=p[p.index("async def semantic"):p.index("async def reason")]
    assert "except LlmUnavailable" in b and "raise" in b
    assert 'semantic_result="UNAVAILABLE"' in l
    assert 'semantic_result="ACCEPTED" if semantic is not None else "REJECTED"' in l

def test_semantic_skills_check_is_symmetric():
    s=src("router/lifecycle/service.py")
    assert '"SKILLS_SEMANTIC_CHECK_STARTED"' in s and '"SKILLS_SEMANTIC_CHECK_COMPLETED"' in s

def test_router_owned_history_wiring():
    assert "list_recent_for_session" in src("router/lifecycle/store.py")
    assert "history_store" in src("router/router_llm_port.py")
    assert "llm_conversation_history_turns" in src("router/config.py")
