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

def test_dashboard_serves_nyra_brand_asset_and_uses_it():
    async def handler(req):
        if req.url.path == '/health':
            return httpx.Response(200, json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'2026-08-30T20:29:52.820197+00:00'})
        return httpx.Response(404)

    rc = RouterClient('http://router', transport=httpx.MockTransport(handler))
    app = create_app(AdminSettings(), rc)
    with TestClient(app) as c:
        dashboard = c.get('/')
        assert dashboard.status_code == 200
        assert '/static/img/nyra.png' in dashboard.text
        logo = c.get('/static/img/nyra.png')
        assert logo.status_code == 200
        assert logo.headers['content-type'] == 'image/png'


def test_admin_includes_browser_local_timestamp_formatter():
    async def handler(req):
        if req.url.path == '/health':
            return httpx.Response(200, json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'x'})
        if req.url.path == '/v1/logs':
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    rc = RouterClient('http://router', transport=httpx.MockTransport(handler))
    app = create_app(AdminSettings(), rc)
    with TestClient(app) as c:
        logs_page = c.get('/logs').text
        assert '/static/js/time.js' in logs_page
        formatter = c.get('/static/js/time.js')
        assert formatter.status_code == 200
        assert 'Intl.DateTimeFormat' in formatter.text
        assert 'timeZoneName' not in formatter.text
        logs_js = c.get('/static/js/logs.js').text
        assert 'formatNyraTimestamp(x.timestamp)' in logs_js

def test_summary_pages_mark_timestamps_for_browser_localization():
    async def handler(req):
        if req.url.path == '/health':
            return httpx.Response(200, json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'x'})
        if req.url.path == '/v1/requests':
            return httpx.Response(200, json=[{
                'request_id':'req_1',
                'start_time':'2026-08-30T20:00:00+00:00',
                'end_time':'2026-08-30T20:00:01+00:00',
                'count':2,
                'result':'success',
                'elapsed_ms':1000,
            }])
        return httpx.Response(200, json=[])

    rc = RouterClient('http://router', transport=httpx.MockTransport(handler))
    app = create_app(AdminSettings(), rc)
    with TestClient(app) as c:
        body = c.get('/requests').text
        assert 'data-nyra-timestamp="2026-08-30T20:00:00+00:00"' in body
        assert 'data-nyra-timestamp="2026-08-30T20:00:01+00:00"' in body

def test_sidebar_contains_nyra_logo_and_dashboard_does_not_duplicate_it():
    async def handler(req):
        if req.url.path == '/health':
            return httpx.Response(200, json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'x'})
        return httpx.Response(200, json=[])

    rc = RouterClient('http://router', transport=httpx.MockTransport(handler))
    app = create_app(AdminSettings(), rc)
    with TestClient(app) as c:
        dashboard = c.get('/').text
        assert '<div class="sidebar-brand">' in dashboard
        assert '<img class="sidebar-logo" src="/static/img/nyra.png"' in dashboard
        assert 'class="dashboard-hero"' not in dashboard


def test_logs_page_uses_responsive_table_container():
    async def handler(req):
        if req.url.path == '/health':
            return httpx.Response(200, json={'service':'nyra-router','version':'0.1','status':'healthy','uptime':1,'timestamp':'x'})
        if req.url.path == '/v1/logs':
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[])

    rc = RouterClient('http://router', transport=httpx.MockTransport(handler))
    app = create_app(AdminSettings(), rc)
    with TestClient(app) as c:
        logs = c.get('/logs').text
        assert '<div class="table-shell">' in logs
        css = c.get('/static/css/admin.css').text
        assert '.table-shell' in css
        assert 'overflow-x:auto' in css.replace(' ', '')
        assert '@media(max-width:800px)' in css.replace(' ', '')
        assert 'minmax(0,1fr)' in css.replace(' ', '')
