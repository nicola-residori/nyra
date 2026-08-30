from datetime import datetime, timezone
from time import monotonic
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from admin.config import AdminSettings
from admin.client import RouterClient
from admin.routes.pages import router as pages_router

def create_app(settings:AdminSettings|None=None, router_client:RouterClient|None=None):
    settings=settings or AdminSettings.load(); started=monotonic(); base=Path(__file__).parent
    app=FastAPI(title="Nyra Admin"); app.state.settings=settings; app.state.router_client=router_client or RouterClient(settings.router_url); app.state.templates=Jinja2Templates(directory=str(base/"templates"))
    app.mount("/static",StaticFiles(directory=str(base/"static")),name="static")
    @app.get("/health")
    def health(): return {"service":"nyra-admin","version":settings.version,"status":"healthy","uptime":round(monotonic()-started,3),"timestamp":datetime.now(timezone.utc).isoformat()}
    app.include_router(pages_router); return app
app=create_app()
