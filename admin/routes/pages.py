from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from admin.client import RouterUnavailable
router=APIRouter()
def templates(req): return req.app.state.templates
async def fetch(req,path,params=None):
    try: return await req.app.state.router_client.get(path,params),None
    except RouterUnavailable as e: return None,str(e)
async def call(req,method,path,params=None,payload=None):
    try: return await req.app.state.router_client.request_json(method,path,params=params,payload=payload),None
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

@router.get("/skills",response_class=HTMLResponse)
async def skills_page(request:Request):
    data,error=await fetch(request,"/v1/admin/skills")
    data=data or {}
    return templates(request).TemplateResponse(request,"skills.html",{
        "service":data.get("service",{"configured":False,"ready":False,"status":"unavailable"}),
        "skills":data.get("skills",[]),
        "jobs":data.get("jobs",[]),
        "capabilities":data.get("capabilities",{}),
        "error":error,
    })

@router.get("/memory/operational",response_class=HTMLResponse)
async def operational_memory(request:Request):
    allowed={"entry_type","scope","owner_user_id","enabled","limit","offset"}
    params={key:value for key,value in request.query_params.items() if key in allowed and value}
    data,error=await fetch(request,"/v1/admin/memory/operational",params)
    return templates(request).TemplateResponse(request,"operational_context.html",{
        "items":(data or {}).get("items",[]),"page":data or {},
        "error":f"Servizio Memory non disponibile: {error}" if error else None,
        "filters":dict(request.query_params),
    })

@router.get("/memory/semantic",response_class=HTMLResponse)
async def semantic_memory(request:Request):
    allowed={"scope","owner_user_id","memory_type","state","limit","offset"}
    params={key:value for key,value in request.query_params.items() if key in allowed and value}
    data,error=await fetch(request,"/v1/admin/memory/semantic",params)
    scores={}
    query=request.query_params.get("q","").strip()
    search_error=None
    if query:
        scopes=[request.query_params.get("scope")] if request.query_params.get("scope") else ["USER","FAMILY","SYSTEM"]
        owner=request.query_params.get("owner_user_id")
        if "USER" in scopes and not owner:
            scopes=[scope for scope in scopes if scope != "USER"]
        search_payload={"query":query,"scopes":scopes}
        if owner and "USER" in scopes: search_payload["owner_user_id"]=owner
        search,search_error=await call(request,"POST","/v1/admin/memory/semantic/search",payload=search_payload)
        scores={item.get("memory_id"):item.get("score") for item in (search or {}).get("items",[])}
    return templates(request).TemplateResponse(request,"semantic_memory.html",{
        "items":(data or {}).get("items",[]),"page":data or {},"scores":scores,
        "error":f"Servizio Memory non disponibile: {error or search_error}" if (error or search_error) else None,
        "filters":dict(request.query_params),
    })

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

@router.api_route("/admin-api/memory/{path:path}",methods=["GET","POST","PUT","DELETE"])
async def memory_proxy(request:Request,path:str):
    router_path=f"/v1/admin/memory/{path}"
    payload=None
    if request.method in {"POST","PUT","DELETE"}:
        try: payload=await request.json()
        except Exception: payload=None
    try:
        data,status_code=await request.app.state.router_client.request_json_with_status(
            request.method,router_path,params=dict(request.query_params),payload=payload)
        return JSONResponse(data,status_code=status_code)
    except RouterUnavailable as exc:
        return JSONResponse({"error":str(exc)},status_code=503)
