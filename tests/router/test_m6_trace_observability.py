from router.observability.service import ObservabilityService
from router.storage.sqlite import SQLiteObservabilityStore
def test_observability_records_correlated_llm_stage(tmp_path):
    store=SQLiteObservabilityStore(tmp_path/"o.sqlite3"); store.initialize(); obs=ObservabilityService(store)
    obs.trace_event("LLM_REASONING_STARTED",request_id="req_00000000-0000-4000-8000-000000000001",origin_request_id="req_00000000-0000-4000-8000-000000000001",trace_id="trc_00000000-0000-4000-8000-000000000001",operation="llm.reason")
    row=store.query_logs({"request_id":"req_00000000-0000-4000-8000-000000000001"})[0]
    assert (row["event"],row["trace_id"],row["operation"])==("LLM_REASONING_STARTED","trc_00000000-0000-4000-8000-000000000001","llm.reason")
