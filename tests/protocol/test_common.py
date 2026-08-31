from shared.protocol.common import CommonOutcome, ErrorDetail
def test_common_outcomes_are_stable_machine_values():
    assert [x.value for x in CommonOutcome]==["SUCCESS","DENIED","NOT_FOUND","AMBIGUOUS","UNAVAILABLE","FAILED","UNSUPPORTED","UNKNOWN_OUTCOME"]
def test_error_detail_has_stable_code_and_optional_diagnostics():
    e=ErrorDetail(code="RESOURCE_NOT_FOUND"); assert e.message is None and e.details is None
