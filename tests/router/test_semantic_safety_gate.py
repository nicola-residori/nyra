import pytest
from router.semantic_skill_bridge import SemanticSkillBridge
from shared.protocol.semantic import SemanticResult
def sem(score=.9,op="TURN_ON",kind="LIGHT",area="soggiorno",params=None,temporal=None):
    return SemanticResult.model_validate({"intent":"control","actions":[{"operation":op,"target":{"reference":"luci","kind":kind,"area":area},"parameters":params or []}],"temporal":temporal,"triggers":[],"conditions":[],"confidence":{"score":score}})
def test_accepts_safe_single_action_with_area(): assert SemanticSkillBridge(.8).accept(sem()) is not None
@pytest.mark.parametrize("value",[sem(score=.79),sem(op="DESTROY"),sem(kind="DOOR"),sem(params=[{"name":"x","value":1}]),sem(temporal={"expression":"domani"}),SemanticResult(intent="x",actions=[],confidence={"score":.99})])
def test_rejects_unsafe_or_uncertain_semantics(value): assert SemanticSkillBridge(.8).accept(value) is None
