from router.config import RouterSettings


def test_lifecycle_config_defaults_and_environment_override(monkeypatch):
    settings=RouterSettings.load()
    assert settings.clarification_timeout_seconds==120
    assert settings.websocket_queue_size==100
    assert settings.memory_url is None
    assert settings.memory_timeout_seconds==3.0
    monkeypatch.setenv("NYRA_CLARIFICATION_TIMEOUT_SECONDS","45")
    monkeypatch.setenv("NYRA_WEBSOCKET_QUEUE_SIZE","25")
    monkeypatch.setenv("NYRA_ROUTER_INGRESS_TOKEN","secret")
    monkeypatch.setenv("NYRA_MEMORY_URL","http://memory.internal:8090")
    monkeypatch.setenv("NYRA_MEMORY_TIMEOUT_SECONDS","1.5")
    settings=RouterSettings.load()
    assert settings.clarification_timeout_seconds==45
    assert settings.websocket_queue_size==25
    assert settings.ingress_token=="secret"
    assert settings.memory_url=="http://memory.internal:8090"
    assert settings.memory_timeout_seconds==1.5
