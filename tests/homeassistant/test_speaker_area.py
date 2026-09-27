from types import SimpleNamespace
from homeassistant.custom_components.nyra.conversation import AdapterInput, build_request, resolve_speaker_area
from homeassistant.custom_components.nyra.session import SessionManager
def E(e,d,area_id=None): return SimpleNamespace(entity_id=e,device_id=d,area_id=area_id,platform="esphome")
def D(d,area_id=None): return SimpleNamespace(id=d,area_id=area_id)
def A(a,n): return SimpleNamespace(id=a,name=n)
def test_entity_area_precedes_device_area():
    assert resolve_speaker_area("assist_satellite.nyra_soggiorno",[E("assist_satellite.nyra_soggiorno","dev","living")],[D("dev","wrong")],[A("living","Soggiorno"),A("wrong","Cucina")]) == "Soggiorno"
def test_device_area_is_fallback():
    assert resolve_speaker_area("assist_satellite.nyra_soggiorno",[E("assist_satellite.nyra_soggiorno","dev")],[D("dev","living")],[A("living","Soggiorno")]) == "Soggiorno"
def test_area_is_never_inferred_from_names():
    assert resolve_speaker_area("assist_satellite.nyra_soggiorno",[E("assist_satellite.nyra_soggiorno","dev")],[D("dev")],[]) is None
def test_request_carries_area():
    r=build_request(AdapterInput("Accendi le luci.","it-IT","speaker:nyra-soggiorno",satellite_id="assist_satellite.nyra_soggiorno",nyra_source_id="nyra-soggiorno",area="Soggiorno"),SessionManager())
    assert r.source.id=="nyra-soggiorno" and r.source.area=="Soggiorno"
