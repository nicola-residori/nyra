from fastapi import APIRouter, Request, Response, status
from shared.protocol.service import ServiceState, ServiceStatusResponse

router = APIRouter()


def _status(request: Request, state: ServiceState, reason: str | None = None) -> ServiceStatusResponse:
    return ServiceStatusResponse(
        status=state,
        service="nyra-router",
        version=request.app.state.settings.version,
        reason=reason,
    )


@router.get("/health", response_model=ServiceStatusResponse)
def health(request: Request) -> ServiceStatusResponse:
    return _status(request, ServiceState.HEALTHY)


@router.get("/ready", response_model=ServiceStatusResponse)
def ready(request: Request, response: Response) -> ServiceStatusResponse:
    if getattr(request.app.state, "ready", False):
        return _status(request, ServiceState.READY)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return _status(request, ServiceState.NOT_READY, "ROUTER_FOUNDATION_NOT_READY")
