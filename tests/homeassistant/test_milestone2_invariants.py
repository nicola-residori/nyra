from homeassistant.custom_components.nyra.const import REQUEST_PATH
from shared.protocol.events import InteractionState


def test_milestone2_has_no_legacy_internal_or_waiting_speaker_states():
    values={x.value for x in InteractionState}
    assert REQUEST_PATH == "/v1/requests"
    assert "WAITING" not in values
    assert not {"MEMORY","SKILL_CHECK","SKILL_EXECUTION","LLM_REASONING","PROCESSING","NEEDS_CLARIFICATION"} & values
