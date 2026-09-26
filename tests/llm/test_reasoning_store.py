import pytest
from llm.reasoning_store import ReasoningStore, ReasoningStateError

def test_create_and_continue_same_trace():
    store=ReasoningStore()
    rid=store.create("trace-a")
    assert store.require(rid,"trace-a").reasoning_id == rid

def test_cross_trace_continuation_is_rejected():
    store=ReasoningStore()
    rid=store.create("trace-a")
    with pytest.raises(ReasoningStateError):
        store.require(rid,"trace-b")

def test_terminal_cleanup_removes_reasoning():
    store=ReasoningStore()
    rid=store.create("trace-a")
    store.complete(rid)
    with pytest.raises(ReasoningStateError):
        store.require(rid,"trace-a")
