import pytest
from pydantic import ValidationError
from shared.protocol.semantic import SemanticAction,SemanticCondition,SemanticParameter,SemanticResult,SemanticTarget,SemanticTemporal,SemanticTrigger
def test_semantic_target_is_reference_not_resolved_resource():
    t=SemanticTarget(reference="lampada dello studio",kind="LIGHT"); d=t.model_dump(); assert d["reference"]=="lampada dello studio" and "resource_id" not in d and "entity_id" not in d
    with pytest.raises(ValidationError): SemanticTarget(reference="x",kind="LIGHT",entity_id="light.x")
def test_semantic_result_represents_understanding_only():
    r=SemanticResult(intent="control",domain="home",actions=[SemanticAction(operation="TURN_ON",target=SemanticTarget(reference="lampada",kind="LIGHT"),parameters=[SemanticParameter(name="brightness",value=50,unit="percent")])],temporal=SemanticTemporal(expression="dopo 10 minuti",relation="AFTER_PREVIOUS"),triggers=[SemanticTrigger(kind="TIME",expression="alle 20")],conditions=[SemanticCondition(kind="STATE",expression="se sono a casa")],interpretation="Turn on later")
    assert r.temporal.relation=="AFTER_PREVIOUS"
    assert {"authorization","entity_id","service_data","execution_plan"}.isdisjoint(SemanticResult.model_fields)

def test_semantic_parameter_can_preserve_expression_without_execution_payload():
    parameter = SemanticParameter(name="temperature", value=None, expression="two degrees warmer")
    assert parameter.expression == "two degrees warmer"
