"""Browser live screencast and control router."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ...browser_stream import browser_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser"])


class BrowserStartRequest(BaseModel):
    url: str | None = None
    width: int | None = 1280
    height: int | None = 800


@router.get("/status")
def get_browser_status():
    return {
        "active": browser_session.is_active,
        "url": browser_session.current_url or None,
        "title": browser_session.current_title or None,
    }


@router.post("/start")
def start_browser(payload: BrowserStartRequest):
    if payload.width and payload.height:
        browser_session.width = payload.width
        browser_session.height = payload.height
    browser_session.start(initial_url=payload.url)
    return {"status": "started", "active": browser_session.is_active}


@router.post("/stop")
def stop_browser():
    browser_session.stop()
    return {"status": "stopped", "active": False}


@router.post("/navigate")
def navigate_browser(payload: BrowserStartRequest):
    if not payload.url:
        return {"status": "error", "message": "URL required"}
    if not browser_session.is_active:
        browser_session.start(initial_url=payload.url)
    else:
        browser_session.navigate(payload.url)
    return {"status": "ok"}


@router.websocket("/ws")
async def browser_websocket(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()

    def on_event(event_type: str, data: dict):
        msg = json.dumps({"type": event_type, "payload": data})
        # Schedule sending to websocket on the asyncio loop
        asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)

    browser_session.add_listener(on_event)

    # If already active, send initial status
    if browser_session.is_active:
        await websocket.send_text(json.dumps({
            "type": "status",
            "payload": {
                "active": True,
                "url": browser_session.current_url or None,
                "title": browser_session.current_title or None,
            }
        }))

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
                msg_type = msg.get("type")
                payload = msg.get("payload", {})

                if msg_type == "start":
                    url = payload.get("url")
                    browser_session.start(initial_url=url)
                elif msg_type == "stop":
                    browser_session.stop()
                elif msg_type == "navigate":
                    url = payload.get("url")
                    if url:
                        browser_session.navigate(url)
                elif msg_type == "reload":
                    browser_session.reload()
                elif msg_type == "mouse":
                    # CDP Input.dispatchMouseEvent
                    browser_session.send_cdp("Input.dispatchMouseEvent", payload)
                elif msg_type == "key":
                    # CDP Input.dispatchKeyEvent
                    browser_session.send_cdp("Input.dispatchKeyEvent", payload)
                elif msg_type == "touch":
                    browser_session.send_cdp("Input.dispatchTouchEvent", payload)
            except Exception as e:
                logger.warning("Error processing websocket message: %s", e)
    except WebSocketDisconnect:
        pass
    finally:
        browser_session.remove_listener(on_event)
