import json,httpx,pytest
from router.skills_client import SkillsClient
from router.llm_action_gate import LlmActionGate
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import ExecutionStep,ExecutionTarget,NyraOperation,NyraResourceType,PlanOrigin,PlanValidationState
from shared.protocol.skills import SkillCorrelation
from shared.protocol.ids import new_request_id, new_trace_id

def plan(origin=PlanOrigin.REASONING_LLM,state=PlanValidationState.PROPOSED):
 return ExecutionPlan(plan_id="p",origin=origin,validation_state=state,steps=[ExecutionStep(step_id="s",operation=NyraOperation.TURN_ON,target=ExecutionTarget(reference="kitchen",resource_type=NyraResourceType.LIGHT))])
def corr(): return SkillCorrelation(request_id=(rid:=new_request_id()),origin_request_id=rid,trace_id=new_trace_id())

@pytest.mark.asyncio
async def test_client_calls_validation_once_and_gate_returns_validated_plan():
 calls=[]
 async def handler(request):
  calls.append(request.url.path); body=json.loads(request.content)
  body["outcome"]="VALIDATED"; body["plan"]["validation_state"]="VALIDATED"; body.pop("trusted_context",None)
  return httpx.Response(200,json=body)
 client=SkillsClient("http://skills",transport=httpx.MockTransport(handler))
 validated=await LlmActionGate(client).validate_proposal(plan(),correlation=corr(),trusted_context={})
 assert validated.validation_state is PlanValidationState.VALIDATED and calls==["/v1/plans/validate"]

@pytest.mark.asyncio
async def test_gate_rejects_forged_origin_and_prevalidated_without_skills_call():
 class Never:
  async def validate_plan(self,*a,**k): raise AssertionError("must not call Skills")
 gate=LlmActionGate(Never())
 with pytest.raises(ValueError): await gate.validate_proposal(plan(PlanOrigin.SKILLS),correlation=corr(),trusted_context={})
 with pytest.raises(ValueError): await gate.validate_proposal(plan(state=PlanValidationState.VALIDATED),correlation=corr(),trusted_context={})
