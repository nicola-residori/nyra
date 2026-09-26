from fastapi import APIRouter,Request
router=APIRouter(prefix="/v1/admin/llm")
@router.get("/diagnostics")
def diagnostics(request:Request):
    items=getattr(request.app.state,"llm_diagnostics",[])
    return {"items":items if isinstance(items,list) else []}
