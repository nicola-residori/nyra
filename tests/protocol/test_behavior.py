from shared.protocol.behavior import *
def test_behavior_contract_and_timeout_default():
    a=BehaviorAction(type=BehaviorActionType.WAIT_CONDITION,condition=BehaviorCondition(kind="STATE",expression="door open")); assert a.timeout_seconds is None and a.on_timeout is WaitTimeoutAction.STOP
    b=Behavior(behavior_id="b",lifecycle=BehaviorLifecycle.ONE_SHOT,triggers=[BehaviorTrigger(kind="TIME",expression="20:00")],conditions=[],actions=[a]); assert b.actions[0] is a
    assert "OR" in (Behavior.model_fields["triggers"].description or "") and "AND" in (Behavior.model_fields["conditions"].description or "")
    assert {"entity_id","service_data","yaml"}.isdisjoint(Behavior.model_fields)
