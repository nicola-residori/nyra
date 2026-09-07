from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
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

@router.get("/identity/profiles",response_class=HTMLResponse)
async def identity_profiles(request:Request):
    data,error=await fetch(request,"/v1/admin/speaker-identity/profiles")
    return templates(request).TemplateResponse(request,"identity_profiles.html",{"profiles":data or [],"error":error})

@router.get("/identity/diagnostics",response_class=HTMLResponse)
async def identity_diagnostics(request:Request):
    params={key:value for key,value in request.query_params.items() if value}
    data,error=await fetch(request,"/v1/admin/speaker-identity/diagnostics",params)
    details={}
    for item in data or []:
        ident=item.get("diagnostic_id")
        if ident:
            detail,_=await fetch(request,f"/v1/admin/speaker-identity/diagnostics/{ident}")
            if detail: details[ident]=detail
    return templates(request).TemplateResponse(request,"identity_diagnostics.html",{"items":data or [],"details":details,"error":error})

@router.get("/wake-words",response_class=HTMLResponse)
async def wake_words(request:Request):
    params={key:value for key,value in request.query_params.items() if value}
    data,error=await fetch(request,"/v1/admin/speaker-identity/wake-words",params)
    return templates(request).TemplateResponse(request,"wake_words.html",{"items":data or [],"error":error})

@router.api_route("/admin-api/speaker-identity/{path:path}",methods=["GET","POST","DELETE"])
async def speaker_identity_proxy(request:Request,path:str):
    router_path=f"/v1/admin/speaker-identity/{path}"
    payload=None
    if request.method in {"POST","DELETE"}:
        try: payload=await request.json()
        except Exception: payload=None
    binary=path.endswith("/audio") or path.endswith("/export")
    try:
        if binary:
            content,content_type,disposition=await request.app.state.router_client.request_bytes(
                request.method,router_path,params=dict(request.query_params),payload=payload)
            headers={"Content-Disposition":disposition} if disposition else None
            return Response(content,media_type=content_type,headers=headers)
        data=await request.app.state.router_client.request_json(
            request.method,router_path,params=dict(request.query_params),payload=payload)
        return JSONResponse(data)
    except RouterUnavailable as exc:
        return JSONResponse({"error":str(exc)},status_code=503)
