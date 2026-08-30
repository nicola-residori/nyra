import httpx
class RouterUnavailable(RuntimeError): pass
class RouterClient:
    def __init__(self,base_url:str, transport=None): self.base_url=base_url.rstrip("/"); self.transport=transport
    async def get(self,path:str,params=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,timeout=3.0,transport=self.transport) as c:
                r=await c.get(path,params=params); r.raise_for_status(); return r.json()
        except httpx.HTTPError as e: raise RouterUnavailable(str(e)) from e
