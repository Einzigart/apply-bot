"""Interactive Browser Streaming Bridge.

Manages headless Chromium contexts, provides real-time CDP Page.screencast frame capture,
and dispatches user mouse/keyboard input safely via a single worker thread.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .config import BROWSER_PROFILE_DIR, STORAGE_STATE_PATH, load_config
from .scrape import _new_page

logger = logging.getLogger(__name__)


class BrowserSession:
    """A thread-safe live browser session streamed over CDP."""

    def __init__(self, width: int = 1280, height: int = 800) -> None:
        self.width = width
        self.height = height
        self.is_active = False
        self.current_url: str = ""
        self.current_title: str = ""

        self._lock = threading.Lock()
        self._listeners: set[Callable[[str, dict], Any]] = set()
        self._cmd_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def add_listener(self, callback: Callable[[str, dict], Any]) -> None:
        with self._lock:
            self._listeners.add(callback)

    def remove_listener(self, callback: Callable[[str, dict], Any]) -> None:
        with self._lock:
            self._listeners.discard(callback)

    def _broadcast(self, event_type: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event_type, data)
            except Exception:
                pass

    def start(self, initial_url: str | None = None) -> None:
        """Start persistent browser session in a dedicated background worker thread."""
        with self._lock:
            if self.is_active and self._thread and self._thread.is_alive():
                if initial_url:
                    self._cmd_queue.put(("navigate", initial_url))
                return

            self._stop_event.clear()
            self._cmd_queue = queue.Queue()
            self._thread = threading.Thread(target=self._worker_loop, args=(initial_url,), daemon=True)
            self._thread.start()

    def _worker_loop(self, initial_url: str | None = None) -> None:
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--no-first-run",
        ]
        kwargs = {
            "user_data_dir": str(BROWSER_PROFILE_DIR),
            "headless": True,
            "args": launch_args,
            "ignore_default_args": ["--enable-automation"],
            "locale": "id-ID",
            "viewport": {"width": self.width, "height": self.height},
        }

        playwright = None
        context = None
        page = None
        cdp = None

        try:
            playwright = sync_playwright().start()
            for ch in ["chrome", "msedge", "chromium", None]:
                try:
                    if ch:
                        context = playwright.chromium.launch_persistent_context(
                            channel=ch,
                            **kwargs,
                        )
                    else:
                        context = playwright.chromium.launch_persistent_context(
                            **kwargs,
                        )
                    break
                except Exception:
                    continue
            else:
                context = playwright.chromium.launch_persistent_context(**kwargs)

            # Sync storage state cookies
            if STORAGE_STATE_PATH.exists():
                try:
                    state_data = json.loads(STORAGE_STATE_PATH.read_text(encoding="utf-8"))
                    cookies = state_data.get("cookies", [])
                    if cookies:
                        context.add_cookies(cookies)
                except Exception:
                    pass

            page = _new_page(context)
            cdp = context.new_cdp_session(page)

            def on_screencast_frame(event: dict) -> None:
                session_id = event.get("sessionId")
                if session_id and cdp:
                    try:
                        cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
                    except Exception:
                        pass
                self._broadcast("frame", {
                    "data": event.get("data"),
                    "metadata": event.get("metadata", {}),
                })

            cdp.on("Page.screencastFrame", on_screencast_frame)

            target_url = initial_url or "https://id.jobstreet.com"
            try:
                page.goto(target_url, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning("Initial navigation error: %s", e)

            with self._lock:
                self.is_active = True
                self.current_url = page.url
                self.current_title = page.title()

            try:
                cdp.send("Page.startScreencast", {
                    "format": "jpeg",
                    "quality": 75,
                    "maxWidth": self.width,
                    "maxHeight": self.height,
                    "everyNthFrame": 1,
                })
            except Exception as e:
                logger.warning("Failed to start screencast: %s", e)

            self._broadcast("status", {"active": True, "url": self.current_url, "title": self.current_title})

            last_url = self.current_url
            last_title = self.current_title
            last_poll = time.time()

            while not self._stop_event.is_set():
                # Process pending commands from queue
                try:
                    while True:
                        cmd, data = self._cmd_queue.get_nowait()
                        if cmd == "navigate" and page and not page.is_closed():
                            page.goto(data, wait_until="domcontentloaded")
                        elif cmd == "reload" and page and not page.is_closed():
                            page.reload()
                        elif cmd == "resize" and page and not page.is_closed():
                            w, h = data
                            try:
                                if cdp:
                                    cdp.send("Emulation.setDeviceMetricsOverride", {
                                        "width": w,
                                        "height": h,
                                        "deviceScaleFactor": 1,
                                        "mobile": False,
                                    })
                                    cdp.send("Page.stopScreencast")
                                    cdp.send("Page.startScreencast", {
                                        "format": "jpeg",
                                        "quality": 75,
                                        "maxWidth": w,
                                        "maxHeight": h,
                                        "everyNthFrame": 1,
                                    })
                                    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 1, "y": 1})
                            except Exception as e:
                                logger.warning("Resize emulation error: %s", e)
                        elif cmd == "cdp" and cdp:
                            method, params = data
                            if method == "Input.dispatchKeyEvent":
                                # If text is provided, also send char event or insertText for typing reliability
                                k_type = params.get("type")
                                text_val = params.get("text")
                                cdp.send(method, params)
                                if k_type == "keyDown" and text_val:
                                    try:
                                        cdp.send("Input.dispatchKeyEvent", {
                                            "type": "char",
                                            "text": text_val,
                                            "unmodifiedText": text_val,
                                            "key": params.get("key", text_val),
                                        })
                                    except Exception:
                                        pass
                            else:
                                cdp.send(method, params)
                        elif cmd == "stop":
                            self._stop_event.set()
                            break
                        self._cmd_queue.task_done()
                except queue.Empty:
                    pass

                if self._stop_event.is_set():
                    break

                if page.is_closed():
                    break

                now = time.time()
                if now - last_poll >= 0.3:
                    last_poll = now
                    try:
                        c_url = page.url
                        c_title = page.title()
                        if c_url != last_url or c_title != last_title:
                            last_url = c_url
                            last_title = c_title
                            with self._lock:
                                self.current_url = c_url
                                self.current_title = c_title
                            self._broadcast("navigated", {"url": c_url, "title": c_title})

                            cookies = context.cookies()
                            has_auth_cookie = any(
                                "session" in c["name"].lower() or "auth" in c["name"].lower() or "token" in c["name"].lower()
                                for c in cookies
                            )
                            if ("/login" not in c_url and "sign" not in c_url and "auth" not in c_url) and has_auth_cookie:
                                STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                                context.storage_state(path=str(STORAGE_STATE_PATH))
                                self._broadcast("session_saved", {"url": c_url})
                    except Exception:
                        pass

                time.sleep(0.02)

        except Exception as e:
            logger.error("Browser session worker error: %s", e)
            self._broadcast("error", {"error": str(e)})
        finally:
            with self._lock:
                self.is_active = False
            try:
                if cdp:
                    cdp.send("Page.stopScreencast")
            except Exception:
                pass
            try:
                if context:
                    STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(STORAGE_STATE_PATH))
                    context.close()
            except Exception:
                pass
            try:
                if playwright:
                    playwright.stop()
            except Exception:
                pass
            self._broadcast("status", {"active": False})

    def send_cdp(self, method: str, params: dict | None = None) -> None:
        """Queue CDP command for the browser thread."""
        if self.is_active:
            self._cmd_queue.put(("cdp", (method, params or {})))

    def navigate(self, url: str) -> None:
        """Queue navigation."""
        if self.is_active:
            self._cmd_queue.put(("navigate", url))
        else:
            self.start(initial_url=url)

    def reload(self) -> None:
        """Queue reload."""
        if self.is_active:
            self._cmd_queue.put(("reload", None))

    def resize(self, width: int, height: int) -> None:
        """Resize viewport dynamically."""
        with self._lock:
            self.width = max(320, min(2560, width))
            self.height = max(240, min(1600, height))
            if self.is_active:
                self._cmd_queue.put(("resize", (self.width, self.height)))

    def stop(self) -> None:
        """Stop browser session and cleanup."""
        self._stop_event.set()
        self._cmd_queue.put(("stop", None))
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        with self._lock:
            self.is_active = False


# Global singleton instance
browser_session = BrowserSession()
