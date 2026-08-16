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

    # Check if a live CDP instance (e.g. from runner pipeline/apply/login) is available
    cdp_ws_url = await get_cdp_ws_url_async()

    if cdp_ws_url:
        logger.info("Connecting directly to live runner CDP: %s", cdp_ws_url)
        try:
            async with websockets.connect(cdp_ws_url) as cdp_ws:
                # 1. Start screencast
                await cdp_ws.send(json.dumps({
                    "id": 1,
                    "method": "Page.startScreencast",
                    "params": {"format": "jpeg", "quality": 70, "maxWidth": 1280, "maxHeight": 800}
                }))

                await websocket.send_text(json.dumps({
                    "type": "status",
                    "payload": {"active": True, "source": "cdp_runner"}
                }))

                async def cdp_to_client():
                    req_id = 100
                    try:
                        async for raw_msg in cdp_ws:
                            data = json.loads(raw_msg)
                            method = data.get("method")
                            if method == "Page.screencastFrame":
                                params = data.get("params", {})
                                session_id = params.get("sessionId")
                                if session_id:
                                    req_id += 1
                                    await cdp_ws.send(json.dumps({
                                        "id": req_id,
                                        "method": "Page.screencastFrameAck",
                                        "params": {"sessionId": session_id}
                                    }))
                                await websocket.send_text(json.dumps({
                                    "type": "frame",
                                    "payload": {
                                        "data": params.get("data"),
                                        "metadata": params.get("metadata", {})
                                    }
                                }))
                            elif method == "Page.navigatedWithinDocument" or method == "Page.frameNavigated":
                                await websocket.send_text(json.dumps({
                                    "type": "navigated",
                                    "payload": {"url": data.get("params", {}).get("frame", {}).get("url")}
                                }))
                    except Exception as e:
                        logger.warning("CDP reader closed: %s", e)

                async def client_to_cdp():
                    msg_id = 500
                    try:
                        while True:
                            client_raw = await websocket.receive_text()
                            msg = json.loads(client_raw)
                            m_type = msg.get("type")
                            payload = msg.get("payload", {})
                            msg_id += 1

                            if m_type == "mouse":
                                await cdp_ws.send(json.dumps({
                                    "id": msg_id,
                                    "method": "Input.dispatchMouseEvent",
                                    "params": payload
                                }))
                            elif m_type == "key":
                                await cdp_ws.send(json.dumps({
                                    "id": msg_id,
                                    "method": "Input.dispatchKeyEvent",
                                    "params": payload
                                }))
                            elif m_type == "navigate":
                                url = payload.get("url")
                                if url:
                                    await cdp_ws.send(json.dumps({
                                        "id": msg_id,
                                        "method": "Page.navigate",
                                        "params": {"url": url}
                                    }))
                            elif m_type == "reload":
                                await cdp_ws.send(json.dumps({
                                    "id": msg_id,
                                    "method": "Page.reload",
                                    "params": {}
                                }))
                    except Exception as e:
                        logger.warning("Client reader closed: %s", e)

                await asyncio.gather(cdp_to_client(), client_to_cdp())
        except Exception as e:
            logger.warning("Direct CDP stream error: %s", e)
            await websocket.send_text(json.dumps({"type": "status", "payload": {"active": False}}))
        return

    # Fallback to internal managed singleton browser session
    def on_event(event_type: str, data: dict):
        msg = json.dumps({"type": event_type, "payload": data})
        asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)

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
                elif msg_type == "reload":
                    browser_session.reload()
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
    finally:
        browser_session.remove_listener(on_event)
