from llm.observability import LlmDiagnostics

def test_privacy_safe_metadata_excludes_sensitive_content():
    d=LlmDiagnostics()
    d.record(purpose="REASONING",outcome="COMPLETED",provider="openai",model="gpt-x",attempt=1,fallback=False,latency_ms=12.5,input_tokens=10,output_tokens=4,valid=True,error_code=None,cost=None)
    item=d.items()[0]
    assert item["purpose"]=="REASONING"
    assert item["cost"] is None
    forbidden={"prompt","messages","history","memory","chain_of_thought","content"}
    assert forbidden.isdisjoint(item)
