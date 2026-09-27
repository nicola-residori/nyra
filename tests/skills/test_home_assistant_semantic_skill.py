from shared.protocol.skills import SkillCheckRequest,SkillCorrelation
from shared.protocol.semantic import SemanticResult
from skills.modules.home_assistant import HomeAssistantActionSkill
class Cap: pass
def req(semantic):
    return SkillCheckRequest(correlation=SkillCorrelation(request_id="req_00000000-0000-4000-8000-000000000001",origin_request_id="req_00000000-0000-4000-8000-000000000001",trace_id="trc_00000000-0000-4000-8000-000000000001"),text="Accendi le luci soggiorno",language="it",semantic=semantic)
def test_semantic_match_uses_operation_type_and_area():
    x=SemanticResult.model_validate({"intent":"control","actions":[{"operation":"TURN_ON","target":{"reference":"luci","kind":"LIGHT","area":"soggiorno"},"parameters":[]}],"triggers":[],"conditions":[],"confidence":{"score":.95}})
    s=HomeAssistantActionSkill(Cap()); assert s.matches(req(x)); m=s.match(req(x))
    assert m.metadata["operation"]=="TURN_ON" and m.metadata["resource_type"]=="LIGHT" and "soggiorno" in m.metadata["reference"].lower()
def test_semantic_match_rejects_temporal_action():
    x=SemanticResult.model_validate({"intent":"control","actions":[{"operation":"TURN_ON","target":{"reference":"luci","kind":"LIGHT","area":"soggiorno"},"parameters":[]}],"temporal":{"expression":"domani"},"triggers":[],"conditions":[],"confidence":{"score":.99}})
    assert not HomeAssistantActionSkill(Cap()).matches(req(x))
