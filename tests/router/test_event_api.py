from pathlib import Path
from fastapi.testclient import TestClient
from router.app import create_app
from router.config import RouterSettings
from shared.protocol.events import IdentityFeedback, IdentityFeedbackEvent, InteractionState, InteractionStateChanged
import asyncio


def test_websocket_auth_subscribe_and_resync(tmp_path: Path):
    app=create_app(RouterSettings(database_path=tmp_path/"router.db", ingress_token="secret"))
    with TestClient(app) as client:
        with client.websocket_connect("/v1/events", headers={"Authorization":"Bearer secret"}) as ws:
            ws.send_json({"action":"subscribe","categories":["interaction_state","identity"]})
            assert ws.receive_json()["type"]=="subscribed"
            asyncio.run(app.state.events.publish_state(InteractionStateChanged(state=InteractionState.PROCESSING_LOCAL, source={"id":"speaker-a"})))
            event=ws.receive_json(); assert event["event"]=="INTERACTION_STATE_CHANGED" and event["state"]=="PROCESSING_LOCAL"
            asyncio.run(app.state.events.publish_identity_feedback(IdentityFeedbackEvent(feedback=IdentityFeedback.RECOGNIZED, source={"id":"speaker-a"})))
            identity=ws.receive_json(); assert identity["event"]=="IDENTITY_FEEDBACK" and identity["feedback"]=="RECOGNIZED"
            ws.send_json({"action":"resync","source_id":"speaker-a"})
            snap=ws.receive_json(); assert snap["type"]=="state_snapshot" and snap["states"][0]["state"]=="PROCESSING_LOCAL"


def test_websocket_rejects_bad_token(tmp_path: Path):
    app=create_app(RouterSettings(database_path=tmp_path/"router.db", ingress_token="secret"))
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/v1/events", headers={"Authorization":"Bearer wrong"}) as ws:
                ws.receive_json()
            assert False, "expected websocket rejection"
        except Exception:
            pass


def test_websocket_lifecycle_is_observable(tmp_path: Path):
    app=create_app(RouterSettings(database_path=tmp_path/"router.db"))
    with TestClient(app) as client:
        with client.websocket_connect("/v1/events") as ws:
            ws.send_json({"action":"subscribe","categories":["interaction_state"]})
            ws.receive_json()
            ws.send_json({"action":"resync"})
            ws.receive_json()
        events=[row["event"] for row in client.get("/v1/logs",params={"q":"WEBSOCKET"}).json()]
        assert "WEBSOCKET_CONNECTED" in events
        assert "WEBSOCKET_SUBSCRIBED" in events
        assert "WEBSOCKET_RESYNC" in events
        assert "WEBSOCKET_DISCONNECTED" in events


def test_websocket_emits_server_heartbeat_when_idle(tmp_path: Path):
    app=create_app(RouterSettings(database_path=tmp_path/"router.db", websocket_heartbeat_seconds=0.01))
    with TestClient(app) as client:
        with client.websocket_connect("/v1/events") as ws:
            heartbeat=ws.receive_json()
            assert heartbeat["type"]=="ping"
