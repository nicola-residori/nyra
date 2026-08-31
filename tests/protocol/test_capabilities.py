from shared.protocol.ids import new_request_id,new_trace_id
from shared.protocol.common import CommonOutcome
from shared.protocol.execution import NyraOperation,NyraResourceType
from shared.protocol.capabilities import *
def test_capability_correlation_has_no_trusted_caller_context():
    forbidden={"session_id","caller","user_id","roles","policy","authorization","token"}; assert forbidden.isdisjoint(CapabilityCorrelation.model_fields)
def test_resolve_and_execute_contracts_are_nyra_native():
    c=CapabilityCorrelation(request_id=new_request_id(),trace_id=new_trace_id())
    ref=ResourceReference(reference="lampada studio",resource_type=NyraResourceType.LIGHT,cardinality=ResolveCardinality.ONE)
    r=ResolveResponse(correlation=c,status=ResolveStatus.NOT_FOUND,reference=ref,candidates=[]); assert r.status is ResolveStatus.NOT_FOUND
    req=ExecuteRequest(correlation=c,operation=NyraOperation.TURN_ON,resource_id="res-1",resource_type=NyraResourceType.LIGHT); assert "service" not in ExecuteRequest.model_fields
def test_idempotency_table_is_exact_and_unknown_outcome_is_representable():
    yes={NyraOperation.TURN_ON,NyraOperation.TURN_OFF,NyraOperation.OPEN,NyraOperation.CLOSE,NyraOperation.SET}
    assert all(is_idempotent_operation(x) for x in yes)
    assert all(not is_idempotent_operation(x) for x in {NyraOperation.TOGGLE,NyraOperation.INCREASE,NyraOperation.DECREASE,NyraOperation.TRIGGER})
    c=CapabilityCorrelation(trace_id=new_trace_id()); resp=ExecuteResponse(correlation=c,outcome=CommonOutcome.UNKNOWN_OUTCOME); assert resp.outcome is CommonOutcome.UNKNOWN_OUTCOME
