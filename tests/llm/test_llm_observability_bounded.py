from llm.observability import LlmDiagnostics
def test_llm_diagnostics_are_bounded():
    d=LlmDiagnostics(max_items=3)
    for i in range(5): d.record(purpose="REASONING",outcome="SUCCESS",provider="p",model=str(i))
    assert [x["model"] for x in d.items()] == ["2","3","4"]
