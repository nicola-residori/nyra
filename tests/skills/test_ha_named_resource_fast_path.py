import pytest
from shared.protocol.capabilities import ExecuteResponse,ResolveCandidate,ResolveResponse,ResolveStatus,ResolvedResource
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation,NyraResourceType
from shared.protocol.skills import SkillCheckRequest,SkillCorrelation,SkillExecuteRequest,SkillOutcome
from skills.modules.home_assistant import HomeAssistantActionSkill
from skills.registry import SkillDefinition,SkillRegistry
from skills.service import SkillsService
RID="req_00000000-0000-4000-8000-000000000001"; TID="trc_00000000-0000-4000-8000-000000000001"
class Cap:
 def __init__(self,resources): self.resources=resources; self.resolve_calls=[]; self.execute_calls=[]
 async def resolve(self,reference,trusted_context,*,correlation):
  self.resolve_calls.append(reference)
  cs=[ResolveCandidate(resource=ResolvedResource(resource_id=e,resource_type=t,name=n),score=2.0) for e,t,n in self.resources]
  return ResolveResponse(correlation=correlation,status=ResolveStatus.RESOLVED if cs else ResolveStatus.NOT_FOUND,reference=reference,candidates=cs)
 async def execute(self,request,trusted_context): self.execute_calls.append(request); return ExecuteResponse(correlation=request.correlation,outcome=CommonOutcome.SUCCESS)
def req(text): return SkillCheckRequest(correlation=SkillCorrelation(request_id=RID,origin_request_id=RID,trace_id=TID),text=text,language="it",context={})
def service(cap):
 skill=HomeAssistantActionSkill(cap); registry=SkillRegistry(); registry.register(SkillDefinition(name=skill.name,priority=skill.priority,matcher=skill.matches,executor=skill.execute)); return SkillsService(registry=registry)
@pytest.mark.asyncio
@pytest.mark.parametrize("entity,rtype",[("script.buonanotte",NyraResourceType.SCRIPT),("scene.modalita_cinema",NyraResourceType.SCENE),("automation.routine_irrigazione",NyraResourceType.AUTOMATION)])
async def test_bare_named_triggerable_resource_is_fast_path(entity,rtype):
 cap=Cap([(entity,rtype,entity.split('.',1)[1].replace('_',' ').title())]); svc=service(cap); response=await svc.check(req(entity.split('.',1)[1].replace('_',' ')))
 assert response.outcome is SkillOutcome.HANDLED and response.match.metadata["operation"]=="TRIGGER" and response.match.metadata["resource_type"]==rtype.value and response.match.metadata["selected_resource_id"]==entity and response.match.metadata["fast_path"]=="named_ha_resource"
 executed=await svc.execute(SkillExecuteRequest(correlation=response.correlation,match=response.match,text="x",language="it",context={}))
 assert executed.outcome is SkillOutcome.HANDLED and cap.execute_calls[0].operation is NyraOperation.TRIGGER and cap.execute_calls[0].resource_id==entity
@pytest.mark.asyncio
async def test_explicit_run_prefix_uses_same_fast_path():
 svc=service(Cap([("script.buonanotte",NyraResourceType.SCRIPT,"Buonanotte")])); response=await svc.check(req("esegui buonanotte")); assert response.outcome is SkillOutcome.HANDLED and response.match.metadata["selected_resource_id"]=="script.buonanotte"
@pytest.mark.asyncio
async def test_no_triggerable_resource_remains_miss_for_llm_fallback():
 response=await service(Cap([])).check(req("perché il cielo è blu")); assert response.outcome is SkillOutcome.MISS
@pytest.mark.asyncio
async def test_fast_path_filters_non_triggerable_resources():
 response=await service(Cap([("light.buonanotte",NyraResourceType.LIGHT,"Buonanotte")])).check(req("buonanotte")); assert response.outcome is SkillOutcome.MISS
@pytest.mark.asyncio
async def test_ambiguous_named_resources_require_clarification_not_llm():
 cap=Cap([("script.relax",NyraResourceType.SCRIPT,"Relax"),("scene.relax",NyraResourceType.SCENE,"Relax")]); svc=service(cap); checked=await svc.check(req("relax")); assert checked.outcome is SkillOutcome.HANDLED
 executed=await svc.execute(SkillExecuteRequest(correlation=checked.correlation,match=checked.match,text="relax",language="it",context={}))
 assert executed.outcome is SkillOutcome.NEEDS_CLARIFICATION and len(executed.pending_state["candidates"])==2 and cap.execute_calls==[]
