import pytest
from homeassistant.custom_components.nyra.config_flow import normalize_router_url


def test_router_url_is_normalized():
    assert normalize_router_url(" http://router:8090/ ") == "http://router:8090"


def test_router_url_requires_http_scheme():
    with pytest.raises(ValueError): normalize_router_url("router:8090")
