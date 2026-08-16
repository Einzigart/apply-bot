import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiFetch } from "../../api/client";

interface BrowserStatus {
  active: boolean;
  url: string | null;
  title: string | null;
}

interface BrowserContextType {
  isOpen: boolean;
  isActive: boolean;
  currentUrl: string;
  currentTitle: string;
  openBrowser: (url?: string) => void;
  closePanel: () => void;
  stopBrowser: () => void;
  navigate: (url: string) => void;
  reload: () => void;
  resizeViewport: (width: number, height: number) => void;
  sendMouseEvent: (type: string, x: number, y: number, button?: string, clickCount?: number) => void;
  sendWheelEvent: (x: number, y: number, deltaX: number, deltaY: number) => void;
  sendKeyEvent: (type: "keyDown" | "keyUp" | "char", key: string, code: string, text?: string, windowsVirtualKeyCode?: number) => void;
  onFrame: ((data: string) => void) | null;
  setOnFrame: (cb: ((data: string) => void) | null) => void;
}

const BrowserContext = createContext<BrowserContextType | null>(null);

export function BrowserProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [currentUrl, setCurrentUrl] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const onFrameCbRef = useRef<((data: string) => void) | null>(null);

  const connectWs = useCallback(() => {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/browser/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[BrowserWS] Connected to live browser streaming");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "frame") {
          if (onFrameCbRef.current && msg.payload?.data) {
            onFrameCbRef.current(msg.payload.data);
          }
        } else if (msg.type === "status") {
          setIsActive(!!msg.payload?.active);
          if (msg.payload?.url) setCurrentUrl(msg.payload.url);
          if (msg.payload?.title) setCurrentTitle(msg.payload.title);
        } else if (msg.type === "navigated") {
          if (msg.payload?.url) setCurrentUrl(msg.payload.url);
          if (msg.payload?.title) setCurrentTitle(msg.payload.title);
        } else if (msg.type === "session_saved") {
          console.log("[BrowserWS] Auth session saved for:", msg.payload?.url);
        }
      } catch (e) {
        console.error("[BrowserWS] Message parse error:", e);
      }
    };

    ws.onclose = () => {
      console.log("[BrowserWS] Disconnected, retrying in 2s...");
      wsRef.current = null;
      setTimeout(connectWs, 2000);
    };

    ws.onerror = (err) => {
      console.warn("[BrowserWS] Connection error:", err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connectWs();
    // Check initial status
    apiFetch<BrowserStatus>("/api/browser/status")
      .then((status) => {
        setIsActive(status.active);
        if (status.url) setCurrentUrl(status.url);
        if (status.title) setCurrentTitle(status.title);
      })
      .catch(() => {});

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWs]);

  const openBrowser = useCallback((url?: string) => {
    setIsOpen(true);
    const targetUrl = url || currentUrl || "https://id.jobstreet.com";
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "start", payload: { url: targetUrl } }));
    } else {
      apiFetch("/api/browser/start", {
        method: "POST",
        body: JSON.stringify({ url: targetUrl }),
      }).catch(console.error);
    }
  }, [currentUrl]);

  const closePanel = useCallback(() => {
    setIsOpen(false);
  }, []);

  const stopBrowser = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "stop" }));
    } else {
      apiFetch("/api/browser/stop", { method: "POST" }).catch(console.error);
    }
    setIsActive(false);
  }, []);

  const navigate = useCallback((url: string) => {
    setCurrentUrl(url);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "navigate", payload: { url } }));
    } else {
      apiFetch("/api/browser/navigate", {
        method: "POST",
        body: JSON.stringify({ url }),
      }).catch(console.error);
    }
  }, []);

  const reload = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "reload" }));
    }
  }, []);

  const resizeViewport = useCallback((width: number, height: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "resize", payload: { width, height } }));
    }
  }, []);

  const sendMouseEvent = useCallback((type: string, x: number, y: number, button = "left", clickCount = 1) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "mouse",
        payload: {
          type,
          x,
          y,
          button: type.includes("mouse") ? button : undefined,
          clickCount: type === "mousePressed" ? clickCount : undefined,
        },
      }));
    }
  }, []);

  const sendWheelEvent = useCallback((x: number, y: number, deltaX: number, deltaY: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "mouse",
        payload: {
          type: "mouseWheel",
          x,
          y,
          deltaX,
          deltaY,
        },
      }));
    }
  }, []);

  const sendKeyEvent = useCallback((type: "keyDown" | "keyUp" | "char", key: string, code: string, text?: string, windowsVirtualKeyCode?: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "key",
        payload: {
          type,
          key,
          code,
          text,
          windowsVirtualKeyCode,
        },
      }));
    }
  }, []);

  const setOnFrame = useCallback((cb: ((data: string) => void) | null) => {
    onFrameCbRef.current = cb;
  }, []);

  return (
    <BrowserContext.Provider
      value={{
        isOpen,
        isActive,
        currentUrl,
        currentTitle,
        openBrowser,
        closePanel,
        stopBrowser,
        navigate,
        reload,
        resizeViewport,
        sendMouseEvent,
        sendWheelEvent,
        sendKeyEvent,
        onFrame: onFrameCbRef.current,
        setOnFrame,
      }}
    >
      {children}
    </BrowserContext.Provider>
  );
}

export function useBrowser() {
  const ctx = useContext(BrowserContext);
  if (!ctx) throw new Error("useBrowser must be used within a BrowserProvider");
  return ctx;
}
