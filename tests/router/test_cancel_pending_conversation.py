import pytest
from router.conversation_control import is_conversation_close
@pytest.mark.parametrize('text',['Annulla tutto.','annulla','lascia stare','cancel'])
def test_cancel_closes_pending_request(text): assert is_conversation_close(text)
@pytest.mark.parametrize('text',['annulla la pulizia','annulla il timer','non annullare tutto'])
def test_specific_or_negated_cancel_is_not_session_close(text): assert not is_conversation_close(text)
