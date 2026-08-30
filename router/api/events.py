from __future__ import annotations
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from shared.protocol.events import EventCategory, EventSubscription
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from router.observability.ids import generate_span_id, generate_trace_id

router = APIRouter(prefix="/v1")


def _authorized(websocket: WebSocket) -> bool:
    token = websocket.app.state.settings.ingress_token
    if not token:
        return True
    return websocket.headers.get("authorization") == f"Bearer {token}"


def _log_websocket(websocket: WebSocket, trace_id: str, span_id: str, event: str, kind: LogKind, **params) -> None:
    websocket.app.state.observability.ingest([LogRecord(
        ct="ROUTER",
        level=LogLevel.INFO,
        kind=kind,
        event=event,
        session_id=None,
        request_id=None,
        trace_id=trace_id,
        span_id=span_id,
        operation="websocket_events",
        params=params,
    )])


@router.websocket("/events")
async def events(websocket: WebSocket):
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    trace_id = generate_trace_id()
    span_id = generate_span_id("ROUTER", "websocket_events")
    _log_websocket(websocket, trace_id, span_id, "WEBSOCKET_CONNECTED", LogKind.REQUEST)
    subscription = None
    try:
        while True:
            receive_task = asyncio.create_task(websocket.receive_json())
            event_task = asyncio.create_task(subscription.queue.get()) if subscription is not None else None
            wait_for = {receive_task} | ({event_task} if event_task is not None else set())
            done, pending = await asyncio.wait(
                wait_for,
                timeout=websocket.app.state.settings.websocket_heartbeat_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if not done:
                await websocket.send_json({"type": "ping"})
                continue
            if event_task is not None and event_task in done:
                event = event_task.result()
                await websocket.send_json(event.model_dump(mode="json"))
                continue
            message = receive_task.result()
            action = message.get("action") if isinstance(message, dict) else None
            if action == "subscribe":
                try:
                    parsed = EventSubscription.model_validate(message)
                except ValidationError as exc:
                    await websocket.send_json({"type":"error","error":"invalid_subscription","details":exc.errors(include_url=False)})
                    continue
                if subscription is not None:
                    await websocket.app.state.events.unsubscribe(subscription)
                subscription = await websocket.app.state.events.subscribe(parsed.categories)
                categories = sorted(x.value for x in parsed.categories)
                _log_websocket(websocket, trace_id, span_id, "WEBSOCKET_SUBSCRIBED", LogKind.EVENT, categories=categories)
                await websocket.send_json({"type":"subscribed","categories":categories})
            elif action == "resync":
                source_id = message.get("source_id")
                snapshots = websocket.app.state.events.snapshot(source_id)
                _log_websocket(websocket, trace_id, span_id, "WEBSOCKET_RESYNC", LogKind.EVENT, source_id=source_id, state_count=len(snapshots))
                await websocket.send_json({"type":"state_snapshot","states":[x.model_dump(mode="json") for x in snapshots]})
            elif action == "ping":
                await websocket.send_json({"type":"pong"})
            else:
                await websocket.send_json({"type":"error","error":"unsupported_action"})
    except WebSocketDisconnect:
        pass
    finally:
        if subscription is not None:
            await websocket.app.state.events.unsubscribe(subscription)
        _log_websocket(websocket, trace_id, span_id, "WEBSOCKET_DISCONNECTED", LogKind.RESPONSE)
