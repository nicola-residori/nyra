from enum import Enum
from pydantic import BaseModel, ConfigDict

class ServiceState(str, Enum):
    HEALTHY = "HEALTHY"
    READY = "READY"
    NOT_READY = "NOT_READY"

class ServiceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ServiceState
    service: str
    version: str
    reason: str | None = None
