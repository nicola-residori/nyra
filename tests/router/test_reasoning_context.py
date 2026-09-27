from router.reasoning_context import build_reasoning_context
from router.lifecycle.service import ContextResult
from tests.router.test_request_lifecycle import request

def test_context_is_minimized_and_trusted():
    ctx=ContextResult(data={"identity":{"user_id":"u","display_name":"N","resolution_source":"TRUSTED_HA_IDENTITY","secret":"x"},"policy":{"role":"user"},"private_blob":"no","timezone":"Europe/Rome"},trace_id="trc_x")
    result=build_reasoning_context(request(kind="ha_assist"),ctx)
    assert result.trusted_identity=={"user_id":"u","display_name":"N","resolution_source":"TRUSTED_HA_IDENTITY"}
    assert "private_blob" not in result.operational
    assert result.operational["trace_id"]=="trc_x"
    assert result.conversation_history==[]
