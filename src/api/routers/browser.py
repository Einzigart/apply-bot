"""Browser live screencast and control router connected to Chrome CDP."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx

from ...config import STORAGE_STATE_PATH
from ...browser_stream import browser_session
import websockets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser"])


async def get_cdp_ws_url_async() -> str | None:
    """Fetch WebSocket debugger URL from Chrome CDP endpoint on port 9222 without blocking event loop."""
    try:
        async with httpx.AsyncClient(timeout=0.2) as client:
            resp = await client.get("http://127.0.0.1:9222/json")
            if resp.status_code == 200:
                targets = resp.json()
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    return pages[0].get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None


@router.get("/status")
async def get_browser_status():
    cdp_url = await get_cdp_ws_url_async()
    if cdp_url:
        return {"active": True, "source": "cdp_remote"}
    return {
        "active": browser_session.is_active,
        "url": browser_session.current_url or None,
        "title": browser_session.current_title or None,
    }


@router.post("/start")
async def start_browser(payload: dict | None = None):
    url = (payload or {}).get("url")
    cdp_url = await get_cdp_ws_url_async()
    if not cdp_url and not browser_session.is_active:
        browser_session.start(initial_url=url)
    return {"status": "started", "active": True}


@router.post("/stop")
def stop_browser():
    browser_session.stop()
    return {"status": "stopped", "active": False}


@router.websocket("/ws")
async def browser_websocket(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()

    # Track active subscriptions
    def on_event(event_type: str, data: dict):
        try:
            msg = json.dumps({"type": event_type, "payload": data})
            asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)
        except Exception:
            pass

    browser_session.add_listener(on_event)

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
                elif msg_type == "go_back":
                    browser_session.go_back()
                elif msg_type == "go_forward":
                    browser_session.go_forward()
                elif msg_type == "reload":
                    browser_session.reload()
                elif msg_type == "resize":
                    w = payload.get("width", 1280)
                    h = payload.get("height", 800)
                    browser_session.resize(w, h)
                elif msg_type == "mouse":
                    browser_session.send_cdp("Input.dispatchMouseEvent", payload)
                elif msg_type == "key":
                    browser_session.send_cdp("Input.dispatchKeyEvent", payload)
                elif msg_type == "touch":
                    browser_session.send_cdp("Input.dispatchTouchEvent", payload)
            except Exception as e:
                logger.warning("Error processing websocket message: %s", e)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Browser websocket connection error: %s", e)
    finally:
        browser_session.remove_listener(on_event)
