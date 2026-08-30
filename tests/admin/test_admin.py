import httpx
from fastapi.testclient import TestClient
from admin.app import create_app
from admin.config import AdminSettings
from admin.client import RouterClient

def test_admin_health_and_pages():
    async def handler(req):
        if req.url.path=='/health': return httpx.Response(200,json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'x'})
        if req.url.path=='/v1/logs': return httpx.Response(200,json=[])
        if req.url.path in ['/v1/requests','/v1/sessions','/v1/traces','/v1/services']: return httpx.Response(200,json=[])
        return httpx.Response(404)
    rc=RouterClient('http://router',transport=httpx.MockTransport(handler))
    app=create_app(AdminSettings(),rc)
    with TestClient(app) as c:
        assert c.get('/health').json()['status']=='healthy'; assert c.get('/').status_code==200
        body=c.get('/logs').text
        for token in ['Search','CT','Level','Kind','Session ID','Request ID','Trace ID','Span ID','Live']: assert token in body
        assert c.get('/requests').status_code==200; assert c.get('/services').status_code==200
