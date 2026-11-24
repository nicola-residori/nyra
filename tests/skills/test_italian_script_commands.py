import pytest
from router.ha_capability import HomeAssistantCapabilityPort
from shared.protocol.capabilities import CapabilityCorrelation, ResourceReference, ResolveStatus
from shared.protocol.execution_common import NyraResourceType
from shared.protocol.skills import SkillOutcome
from skills.modules.home_assistant import parse_command, HomeAssistantActionSkill
from skills.registry import SkillDefinition, SkillRegistry
from skills.service import SkillsService
from tests.skills.test_ha_named_resource_fast_path import req

class Inventory:
    async def states(self):
        return [{'entity_id':e,'attributes':{'friendly_name':n}} for e,n in [
            ('script.buonanotte','Buonanotte'),
            ('script.pulizia_zona_giorno_standard','Zona Giorno - Pulizia'),
            ('script.pulizia_zona_giorno_aspirazione','Zona Giorno - Aspirazione'),
            ('script.pulizia_zona_giorno_profonda','Zona Giorno - Pulizia profonda')]]
    async def area_entities(self, area): return set()

@pytest.mark.parametrize('text,reference',[
    ('esegui lo script della buonanotte','buonanotte'),
    ('pulisci zona giorno','pulizia zona giorno standard'),
    ('aspira la zona giorno','pulizia zona giorno aspirazione'),
    ('pulisci profondamente zona giorno','pulizia zona giorno profonda'),
    ('pulisci a fondo la zona giorno','pulizia zona giorno profonda'),
])
def test_script_parser(text,reference):
    p=parse_command(text,'it')
    assert p and p.resource_type is NyraResourceType.SCRIPT and p.operation.value=='TRIGGER' and p.reference==reference

@pytest.mark.asyncio
async def test_global_script_is_not_filtered_by_current_speaker_room():
    p=HomeAssistantCapabilityPort(Inventory())
    r=await p.resolve(ResourceReference(reference='buonanotte',resource_type=NyraResourceType.SCRIPT),{'area':'Soggiorno'},correlation=CapabilityCorrelation(request_id=req('x').correlation.request_id,trace_id=req('x').correlation.trace_id))
    assert r.status is ResolveStatus.RESOLVED and r.candidates[0].resource.resource_id=='script.buonanotte'

@pytest.mark.asyncio
async def test_unstructured_target_correction_reaches_llm_instead_of_reusing_wrong_kind():
    skill=HomeAssistantActionSkill(HomeAssistantCapabilityPort(Inventory()))
    registry=SkillRegistry();registry.register(SkillDefinition(name=skill.name,priority=skill.priority,matcher=skill.matches,executor=skill.execute))
    r=req('intendevo quello per andare a dormire').model_copy(update={'pending_state':{'llm_clarification':{'reason':'HA_TARGET_NOT_FOUND','skill_name':skill.name,'resource_type':'SCENE','operation':'TRIGGER'}}})
    assert (await SkillsService(registry=registry).check(r)).outcome is SkillOutcome.MISS

@pytest.mark.asyncio
@pytest.mark.parametrize('text,entity',[
    ('esegui lo script della buonanotte','script.buonanotte'),
    ('È uno script, si chiama buonanotte.','script.buonanotte'),
    ('attiva la buonanotte','script.buonanotte'),
    ('pulisci zona giorno','script.pulizia_zona_giorno_standard'),
    ('aspira zona giorno','script.pulizia_zona_giorno_aspirazione'),
    ('pulisci profondamente zona giorno','script.pulizia_zona_giorno_profonda'),
])
async def test_strict_inventory_executes_only_requested_script_in_simulation(text,entity):
    from shared.protocol.skills import SkillExecuteRequest
    class RecordingInventory(Inventory):
        def __init__(self): self.calls=[]
        async def invoke(self, domain, service, entity_id, parameters): self.calls.append((domain,service,entity_id,parameters))
        async def state(self, entity_id): return next((s for s in await self.states() if s['entity_id']==entity_id),None)
    inv=RecordingInventory();skill=HomeAssistantActionSkill(HomeAssistantCapabilityPort(inv))
    r=req(text).model_copy(update={'context':{'area':'Soggiorno'}, **({'pending_state':{'llm_clarification':{'reason':'HA_TARGET_NOT_FOUND','skill_name':skill.name,'resource_type':'SCENE','operation':'TRIGGER'}}} if text.startswith('È') else {})})
    match=skill.match(r) if skill.matches(r) else await skill.fast_path_match(r)
    result=await skill.execute(SkillExecuteRequest(correlation=r.correlation,match=match,text=text,language='it',context=r.context))
    assert result.outcome is SkillOutcome.HANDLED
    assert inv.calls==[('script','turn_on',entity,{})]

@pytest.mark.asyncio
async def test_unavailable_aspiration_never_substitutes_other_mode():
    from shared.protocol.skills import SkillExecuteRequest
    class NoAspiration(Inventory):
        async def states(self): return [s for s in await super().states() if not s['entity_id'].endswith('_aspirazione')]
        async def invoke(self,*a): pytest.fail('must not execute a different mode')
    skill=HomeAssistantActionSkill(HomeAssistantCapabilityPort(NoAspiration()));r=req('aspira zona giorno')
    result=await skill.execute(SkillExecuteRequest(correlation=r.correlation,match=skill.match(r),text=r.text,language='it',context={}))
    assert result.outcome is SkillOutcome.NEEDS_CLARIFICATION

@pytest.mark.parametrize('text',['non pulisci zona giorno','come pulisci zona giorno','se pulisci zona giorno','pulisci'])
def test_noncommands_or_missing_zone_are_not_deterministic_actions(text): assert parse_command(text,'it') is None

@pytest.mark.parametrize('text',['pulisci zona giorno a fondo','pulisci solo aspirando zona giorno','pulisci zona giorno domani','È uno script, si chiama buonanotte.'])
def test_alternative_or_declarative_wording_defers_to_semantic_context(text):
    assert parse_command(text,'it') is None

@pytest.mark.asyncio
async def test_declarative_correction_only_uses_pending_action_context():
    skill=HomeAssistantActionSkill(HomeAssistantCapabilityPort(Inventory()))
    r=req('È uno script, si chiama buonanotte.')
    assert not skill.matches(r)
    r=r.model_copy(update={'pending_state':{'llm_clarification':{'reason':'HA_TARGET_NOT_FOUND','skill_name':skill.name,'resource_type':'SCENE','operation':'TRIGGER'}}})
    assert skill.matches(r)
    assert skill.match(r).metadata['resource_type']=='SCRIPT'
    assert skill.match(r).metadata['reference']=='buonanotte'
