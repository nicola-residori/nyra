import json
from llm.prompts import reasoning_messages
from shared.protocol.llm import LlmPurpose, LlmRequest, ReasoningContext


def test_provider_receives_supported_read_tool_parameter_contract():
    request = LlmRequest(purpose=LlmPurpose.REASONING, context=ReasoningContext(language="it", current_user_input="resoconto fotovoltaico"))
    payload = json.loads(reasoning_messages(request)[0]["content"])
    assert set(payload["read_tools"]) == {"DISCOVER_RESOURCES", "READ_STATE", "READ_ATTRIBUTE", "SEARCH_MEMORY"}
    assert set(payload["read_tools"]["DISCOVER_RESOURCES"]["parameters"]) == {"query"}
    assert set(payload["read_tools"]["READ_ATTRIBUTE"]["parameters"]) == {"entity_id", "attribute"}
