from datetime import datetime, timezone
from fastapi import APIRouter, Request
router=APIRouter()
@router.get("/health")
def health(request: Request):
    s=request.app.state.settings
    return {"service":"nyra-router","version":s.version,"status":"healthy","uptime":request.app.state.uptime(),"timestamp":datetime.now(timezone.utc).isoformat()}
