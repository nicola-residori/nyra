from fastapi import APIRouter, Request, Query, HTTPException
router=APIRouter(prefix="/v1")
@router.get("/logs")
def logs(request: Request, q:str|None=None,ct:str|None=None,level:str|None=None,kind:str|None=None,event:str|None=None,result:str|None=None,
         session_id:str|None=None,request_id:str|None=None,trace_id:str|None=None,span_id:str|None=None,from_ts:str|None=None,to_ts:str|None=None,
         limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0)):
    f=locals(); f.pop("request"); return request.app.state.store.query_logs(f)
@router.get("/requests")
def requests(request: Request): return request.app.state.store.list_requests()
@router.get("/requests/{ident}")
def request_detail(request: Request, ident:str): return _get(request.app.state.store.get_request(ident))
@router.get("/sessions")
def sessions(request: Request): return request.app.state.store.list_sessions()
@router.get("/sessions/{ident}")
def session_detail(request: Request, ident:str): return _get(request.app.state.store.get_session(ident))
@router.get("/traces")
def traces(request: Request): return request.app.state.store.list_traces()
@router.get("/traces/{ident}")
def trace_detail(request: Request, ident:str):
    data=_get(request.app.state.store.get_trace(ident)); logs=data["logs"]
    data["spans"]=[{"span_id":x["span_id"],"parent_span_id":x["parent_span_id"],"ct":x["ct"],"operation":x["operation"],"span_elapsed_ms":x["span_elapsed_ms"]} for x in logs]
    return data
@router.get("/spans/{ident}")
def span_detail(request: Request, ident:str): return _get(request.app.state.store.get_span(ident))
@router.get("/services")
def services(request: Request): return [{"name":"nyra-router","endpoint":f"http://127.0.0.1:{request.app.state.settings.port}","health":"healthy"}]
def _get(data):
    if data is None: raise HTTPException(status_code=404,detail="not found")
    return data
