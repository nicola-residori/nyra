from homeassistant.custom_components.nyra.session import SessionManager


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def test_same_conversation_reuses_session():
    manager = SessionManager(clock=Clock())
    first = manager.get_or_create_session("conversation-a")
    second = manager.get_or_create_session("conversation-a")
    assert first == second


def test_terminal_request_gets_new_request_next_turn():
    manager = SessionManager(clock=Clock())
    first = manager.get_request_id("conversation-a")
    manager.complete_request("conversation-a")
    second = manager.get_request_id("conversation-a")
    assert first != second


def test_clarification_preserves_request():
    manager = SessionManager(clock=Clock())
    first = manager.get_request_id("conversation-a")
    manager.preserve_request("conversation-a")
    assert manager.get_request_id("conversation-a") == first


def test_expired_conversation_gets_new_session():
    clock = Clock()
    manager = SessionManager(ttl_seconds=10, clock=clock)
    first = manager.get_or_create_session("conversation-a")
    clock.now = 11
    manager.expire()
    assert manager.get_or_create_session("conversation-a") != first
