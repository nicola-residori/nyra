from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from router.llm_client import LlmUnavailable
router=APIRouter(prefix="/v1/admin/llm")
@router.get("/diagnostics")
async def diagnostics(request:Request):
    client=getattr(request.app.state,"llm_client",None)
    if client is None: return {"items":[]}
    try: return await client.diagnostics()
    except LlmUnavailable: return JSONResponse({"items":[],"error":"LLM_UNAVAILABLE"},status_code=503)
