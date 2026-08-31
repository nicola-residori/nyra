from shared.protocol.service import ServiceState, ServiceStatusResponse
def test_service_status_contract_is_small_and_explicit():
    assert [x.value for x in ServiceState]==["HEALTHY","READY","NOT_READY"]
    r=ServiceStatusResponse(status=ServiceState.NOT_READY,service="nyra-router",version="0.1.0",reason="STORAGE_UNAVAILABLE")
    assert r.reason=="STORAGE_UNAVAILABLE"
    assert {"authorization","token","data","payload","result"}.isdisjoint(ServiceStatusResponse.model_fields)
