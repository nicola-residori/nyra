from __future__ import annotations
from shared.protocol.common import ErrorDetail
from shared.protocol.execution_common import NyraOperation,NyraResourceType,PlanValidationState
from shared.protocol.skills import PlanValidationRequest,PlanValidationResponse,PlanValidationOutcome

_ALLOWED={
 (NyraResourceType.LIGHT,NyraOperation.TURN_ON),(NyraResourceType.LIGHT,NyraOperation.TURN_OFF),
 (NyraResourceType.SWITCH,NyraOperation.TURN_ON),(NyraResourceType.SWITCH,NyraOperation.TURN_OFF),
 (NyraResourceType.COVER,NyraOperation.OPEN),(NyraResourceType.COVER,NyraOperation.CLOSE),
 (NyraResourceType.SCRIPT,NyraOperation.TRIGGER),(NyraResourceType.SCENE,NyraOperation.TRIGGER),
}
_SAFE_PARAMS={"brightness","brightness_pct","temperature","hvac_mode","position","volume_level"}

class PlanValidator:
    async def validate(self,request:PlanValidationRequest)->PlanValidationResponse:
        for step in request.plan.steps:
            if (step.target.resource_type,step.operation) not in _ALLOWED:
                return PlanValidationResponse(correlation=request.correlation,outcome=PlanValidationOutcome.REJECTED,error=ErrorDetail(code="UNSUPPORTED_ACTION"))
            if not set(step.parameters)<=_SAFE_PARAMS:
                return PlanValidationResponse(correlation=request.correlation,outcome=PlanValidationOutcome.REJECTED,error=ErrorDetail(code="UNSUPPORTED_PARAMETERS"))
        validated=request.plan.model_copy(update={"validation_state":PlanValidationState.VALIDATED})
        return PlanValidationResponse(correlation=request.correlation,outcome=PlanValidationOutcome.VALIDATED,plan=validated)
