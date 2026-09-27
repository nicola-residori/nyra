import json
import httpx
import pytest
from router.ha_capability import HomeAssistantApiClient, HomeAssistantCapabilityPort
from shared.protocol.capabilities import CapabilityCorrelation, ResolveCardinality, ResourceReference
from shared.protocol.execution_common import NyraResourceType
def corr():
    return CapabilityCorrelation(trace_id="trc_123e4567-e89b-42d3-a456-426614174000",span_id="ROUTER#test#AREA")
@pytest.mark.asyncio
async def test_area_entities_uses_home_assistant_area_registry_semantics():
    async def handler(request):
        assert request.url.path == "/api/template"
        body=json.loads(request.content)
        assert "area_entities" in body["template"] and "Soggiorno" in body["template"]
        return httpx.Response(200,json=["light.pianta","light.tavolo"])
    c=HomeAssistantApiClient("http://ha","token",transport=httpx.MockTransport(handler))
    assert await c.area_entities("Soggiorno") == {"light.pianta","light.tavolo"}
@pytest.mark.asyncio
async def test_resolve_many_filters_by_real_ha_area_not_friendly_name():
    async def handler(request):
        if request.url.path == "/api/template": return httpx.Response(200,json=["light.pianta","light.tavolo"])
        if request.url.path == "/api/states": return httpx.Response(200,json=[
            {"entity_id":"light.pianta","state":"off","attributes":{"friendly_name":"Pianta"}},
            {"entity_id":"light.tavolo","state":"off","attributes":{"friendly_name":"Tavolo"}},
            {"entity_id":"light.cucina","state":"off","attributes":{"friendly_name":"Luce cucina"}}])
        raise AssertionError(request.url.path)
    p=HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha","token",transport=httpx.MockTransport(handler)))
    out=await p.resolve(ResourceReference(reference="luce",resource_type=NyraResourceType.LIGHT,cardinality=ResolveCardinality.MANY),{"area":"Soggiorno"},correlation=corr())
    assert [x.resource.resource_id for x in out.candidates] == ["light.pianta","light.tavolo"]
@pytest.mark.asyncio
async def test_explicit_reference_does_not_apply_implicit_speaker_area():
    async def handler(request):
        assert request.url.path == "/api/states"
        return httpx.Response(200,json=[{"entity_id":"light.cucina","state":"off","attributes":{"friendly_name":"Luce cucina"}}])
    p=HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha","token",transport=httpx.MockTransport(handler)))
    out=await p.resolve(ResourceReference(reference="luce cucina",resource_type=NyraResourceType.LIGHT,cardinality=ResolveCardinality.MANY),{"area":"Soggiorno"},correlation=corr())
    assert [x.resource.resource_id for x in out.candidates] == ["light.cucina"]

@pytest.mark.asyncio
async def test_explicit_area_resolves_by_registry_membership():
    async def handler(request):
        if request.url.path == "/api/template":
            body=json.loads(request.content)
            assert "Cucina" in body["template"]
            return httpx.Response(200,json=["light.pensili","light.tavolo_cucina"])
        if request.url.path == "/api/states":
            return httpx.Response(200,json=[
                {"entity_id":"light.pensili","state":"off","attributes":{"friendly_name":"Pensili"}},
                {"entity_id":"light.tavolo_cucina","state":"off","attributes":{"friendly_name":"Tavolo"}},
                {"entity_id":"light.pianta","state":"off","attributes":{"friendly_name":"Pianta"}}])
        raise AssertionError(request.url.path)
    p=HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha","token",transport=httpx.MockTransport(handler)))
    out=await p.resolve(ResourceReference(reference="luce",resource_type=NyraResourceType.LIGHT,cardinality=ResolveCardinality.MANY),{"area":"Cucina"},correlation=corr())
    assert [x.resource.resource_id for x in out.candidates] == ["light.pensili","light.tavolo_cucina"]

@pytest.mark.asyncio
async def test_unknown_area_does_not_fall_back_globally():
    async def handler(request):
        if request.url.path == "/api/template": return httpx.Response(200,json=[])
        if request.url.path == "/api/states": return httpx.Response(200,json=[{"entity_id":"light.pianta","state":"off","attributes":{"friendly_name":"Pianta"}}])
        raise AssertionError(request.url.path)
    p=HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha","token",transport=httpx.MockTransport(handler)))
    out=await p.resolve(ResourceReference(reference="luce",resource_type=NyraResourceType.LIGHT,cardinality=ResolveCardinality.MANY),{"area":"Area inesistente"},correlation=corr())
    assert out.candidates == []
