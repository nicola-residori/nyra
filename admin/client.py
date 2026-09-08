import httpx
class RouterUnavailable(RuntimeError): pass
class RouterClient:
    def __init__(self,base_url:str, transport=None, token:str|None=None): self.base_url=base_url.rstrip("/"); self.transport=transport; self.token=token
    def _headers(self): return {"Authorization":f"Bearer {self.token}"} if self.token else None
    async def get(self,path:str,params=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=3.0,transport=self.transport) as c:
                r=await c.get(path,params=params,headers=self._headers()); r.raise_for_status(); return r.json()
        except httpx.HTTPError as e: raise RouterUnavailable(str(e)) from e
    async def request_json(self,method:str,path:str,params=None,payload=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=10.0,transport=self.transport) as c:
                r=await c.request(method,path,params=params,json=payload,headers=self._headers()); r.raise_for_status(); return r.json()
        except (httpx.HTTPError,ValueError) as e: raise RouterUnavailable(str(e)) from e
    async def request_json_with_status(self,method:str,path:str,params=None,payload=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=10.0,transport=self.transport) as c:
                r=await c.request(method,path,params=params,json=payload,headers=self._headers()); return r.json(),r.status_code
        except (httpx.HTTPError,ValueError) as e: raise RouterUnavailable(str(e)) from e
    async def request_bytes(self,method:str,path:str,params=None,payload=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=30.0,transport=self.transport) as c:
                r=await c.request(method,path,params=params,json=payload,headers=self._headers()); r.raise_for_status()
                return r.content,r.headers.get("content-type","application/octet-stream"),r.headers.get("content-disposition")
        except httpx.HTTPError as e: raise RouterUnavailable(str(e)) from e
