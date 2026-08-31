import pytest
from pydantic import ValidationError
from shared.protocol.ids import new_request_id,new_session_id,new_trace_id
from shared.protocol.context import IdentityResolutionSource,ResolvedIdentity,RequestContext,RequestType
def test_request_and_identity_values_are_stable():
    assert [x.value for x in RequestType]==["ha_assist","ha_speaker","job","nyra_ui"]
    assert {x.value for x in IdentityResolutionSource}=={"TRUSTED_HA_IDENTITY","SPEAKER_IDENTIFICATION","SESSION_CONTINUITY","GUEST_FALLBACK"}
def test_source_and_identity_are_independent():
    c=RequestContext(session_id=new_session_id(),request_id=new_request_id(),trace_id=new_trace_id(),type=RequestType.HA_SPEAKER,language="it",source="nyra-soggiorno",area="living_room",identity=ResolvedIdentity(user_id="user-123",resolution_source=IdentityResolutionSource.SPEAKER_IDENTIFICATION))
    assert c.source=="nyra-soggiorno" and c.identity.user_id=="user-123"
def test_interactive_requires_session_request_but_job_does_not():
    with pytest.raises(ValidationError): RequestContext(trace_id=new_trace_id(),type=RequestType.HA_ASSIST,language="it")
    job=RequestContext(trace_id=new_trace_id(),type=RequestType.JOB,language="it"); assert job.session_id is None and job.request_id is None
