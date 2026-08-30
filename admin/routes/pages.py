from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from admin.client import RouterUnavailable
router=APIRouter()
def templates(req): return req.app.state.templates
async def fetch(req,path,params=None):
    try: return await req.app.state.router_client.get(path,params),None
    except RouterUnavailable as e: return None,str(e)
@router.get("/",response_class=HTMLResponse)
async def dashboard(request:Request):
    health,error=await fetch(request,"/health"); logs,_=await fetch(request,"/v1/logs",{"limit":1})
    return templates(request).TemplateResponse(request,"dashboard.html",{"router_health":health,"router_error":error,"log_count_hint":len(logs or [])})
@router.get("/logs",response_class=HTMLResponse)
async def logs_page(request:Request): return templates(request).TemplateResponse(request,"logs.html",{})
@router.get("/admin-api/logs")
async def logs_proxy(request:Request):
    data,error=await fetch(request,"/v1/logs",dict(request.query_params)); return JSONResponse({"items":data or [],"error":error})
@router.get("/requests",response_class=HTMLResponse)
async def requests(request:Request): data,error=await fetch(request,"/v1/requests"); return templates(request).TemplateResponse(request,"requests.html",{"items":data or [],"error":error})
@router.get("/sessions",response_class=HTMLResponse)
async def sessions(request:Request): data,error=await fetch(request,"/v1/sessions"); return templates(request).TemplateResponse(request,"sessions.html",{"items":data or [],"error":error})
@router.get("/traces",response_class=HTMLResponse)
async def traces(request:Request): data,error=await fetch(request,"/v1/traces"); return templates(request).TemplateResponse(request,"traces.html",{"items":data or [],"error":error})
@router.get("/traces/{ident}",response_class=HTMLResponse)
async def trace_detail(request:Request,ident:str): data,error=await fetch(request,f"/v1/traces/{ident}"); return templates(request).TemplateResponse(request,"trace_detail.html",{"trace":data,"error":error})
@router.get("/services",response_class=HTMLResponse)
async def services(request:Request): data,error=await fetch(request,"/v1/services"); return templates(request).TemplateResponse(request,"services.html",{"items":data or [],"error":error})
