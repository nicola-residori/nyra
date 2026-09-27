import json
from llm.prompts import semantic_messages
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningContext

def _message(mode=None):
    operational={} if mode is None else {"mode":mode}
    req=LlmRequest(purpose=LlmPurpose.SEMANTIC,context=ReasoningContext(
        language="it",current_user_input="Accendi le luci soggiorno",operational=operational))
    return json.loads(semantic_messages(req)[0]["content"])

def test_skill_routing_semantic_requires_confidence_and_canonical_control_contract():
    payload=_message("skill_routing")
    contract=payload["contract"]
    assert "confidence" in contract.lower()
    assert "TURN_ON" in contract and "LIGHT" in contract
    assert "area" in contract

def test_generic_semantic_prompt_is_not_forced_into_skill_routing_contract():
    payload=_message()
    assert "contract" not in payload
