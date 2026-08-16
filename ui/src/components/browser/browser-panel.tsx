import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  X,
  RotateCw,
  ArrowRight,
  ExternalLink,
  Power,
  Maximize2,
  Minimize2,
  ShieldCheck,
  Globe,
  Loader2,
  GripVertical,
} from "lucide-react";
import { useBrowser } from "./browser-context";

export function BrowserPanel() {
  const {
    isOpen,
    isActive,
    currentUrl,
    currentTitle,
    closePanel,
    stopBrowser,
    navigate,
    reload,
    resizeViewport,
    sendMouseEvent,
    sendWheelEvent,
    sendKeyEvent,
    setOnFrame,
  } = useBrowser();

  const [inputUrl, setInputUrl] = useState(currentUrl || "");
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [panelWidth, setPanelWidth] = useState<number>(640);
  const [isResizing, setIsResizing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [lastFrameTime, setLastFrameTime] = useState<number>(0);
  const [viewportDims, setViewportDims] = useState<{ width: number; height: number }>({ width: 1280, height: 800 });

  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const resizeTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    setInputUrl(currentUrl);
  }, [currentUrl]);

  useEffect(() => {
    setOnFrame((data: string) => {
      setFrameSrc(`data:image/jpeg;base64,${data}`);
      setLastFrameTime(Date.now());
    });
    return () => {
      setOnFrame(null);
    };
  }, [setOnFrame]);

  // Handle panel dragging resize
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(380, Math.min(window.innerWidth - 60, window.innerWidth - e.clientX));
      setPanelWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  // Dynamically sync container size to backend browser viewport
  const updateViewportSize = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const w = Math.round(rect.width);
    const h = Math.round(rect.height);
    if (w > 100 && h > 100 && (w !== viewportDims.width || h !== viewportDims.height)) {
      setViewportDims({ width: w, height: h });
      if (resizeTimeoutRef.current) {
        window.clearTimeout(resizeTimeoutRef.current);
      }
      resizeTimeoutRef.current = window.setTimeout(() => {
        resizeViewport(w, h);
      }, 150);
    }
  }, [viewportDims, resizeViewport]);

  useEffect(() => {
    if (isOpen) {
      updateViewportSize();
    }
  }, [panelWidth, isFullscreen, isOpen, updateViewportSize]);

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUrl.trim()) return;
    let url = inputUrl.trim();
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = "https://" + url;
    }
    navigate(url);
  };

  // Precise coordinates mapping from dynamic canvas/img to viewport
  const getCdpCoords = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!imageRef.current) return { x: 0, y: 0 };
    const rect = imageRef.current.getBoundingClientRect();
    const targetW = viewportDims.width || 1280;
    const targetH = viewportDims.height || 800;
    const scaleX = targetW / rect.width;
    const scaleY = targetH / rect.height;
    const x = Math.max(0, Math.min(targetW, (e.clientX - rect.left) * scaleX));
    const y = Math.max(0, Math.min(targetH, (e.clientY - rect.top) * scaleY));
    return { x: Math.round(x), y: Math.round(y) };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLImageElement>) => {
    const { x, y } = getCdpCoords(e);
    sendMouseEvent("mouseMoved", x, y);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLImageElement>) => {
    const { x, y } = getCdpCoords(e);
    const button = e.button === 2 ? "right" : e.button === 1 ? "middle" : "left";
    sendMouseEvent("mousePressed", x, y, button, e.detail || 1);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLImageElement>) => {
    const { x, y } = getCdpCoords(e);
    const button = e.button === 2 ? "right" : e.button === 1 ? "middle" : "left";
    sendMouseEvent("mouseReleased", x, y, button, 1);
  };

  const handleWheel = (e: React.WheelEvent<HTMLImageElement>) => {
    const { x, y } = getCdpCoords(e);
    sendWheelEvent(x, y, e.deltaX, e.deltaY);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isFocused) return;
    if (e.key === "Tab") {
      e.preventDefault();
    }
    sendKeyEvent("keyDown", e.key, e.code, e.key.length === 1 ? e.key : undefined, e.keyCode);
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      sendKeyEvent("char", e.key, e.code, e.key, e.keyCode);
    }
  };

  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (!isFocused) return;
    sendKeyEvent("keyUp", e.key, e.code, undefined, e.keyCode);
  };

  if (!isOpen) return null;

  return (
    <aside
      style={isFullscreen ? { width: "100vw", left: 0 } : { width: `${panelWidth}px` }}
      className={`fixed top-0 right-0 h-screen z-50 flex flex-col bg-neutral-900 border-l border-neutral-800 shadow-2xl transition-[width] duration-75 select-none ${
        isResizing ? "select-none pointer-events-none" : ""
      }`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
    >
      {/* Draggable Left Resize Handle */}
      {!isFullscreen && (
        <div
          onMouseDown={() => setIsResizing(true)}
          className="absolute left-0 top-0 bottom-0 w-2.5 -translate-x-1/2 cursor-ew-resize hover:bg-blue-500/40 z-50 flex items-center justify-center group"
          title="Drag to resize browser width"
        >
          <div className="w-1 h-8 rounded-full bg-neutral-600/60 group-hover:bg-blue-400 group-hover:h-12 transition-all flex items-center justify-center">
            <GripVertical size={8} className="text-white opacity-0 group-hover:opacity-100" />
          </div>
        </div>
      )}

      {/* Top Header / Browser Chrome */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-neutral-950 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-neutral-800/80 text-[11px] font-medium text-neutral-300">
            <span
              className={`w-2 h-2 rounded-full ${
                isActive ? "bg-emerald-500 animate-pulse" : "bg-neutral-500"
              }`}
            />
            <span>{isActive ? "Browser Live" : "Browser Inactive"}</span>
          </div>
          <span className="text-xs text-neutral-400 font-medium truncate max-w-[220px]">
            {currentTitle || "Embedded Browser"}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
            title={isFullscreen ? "Restore window" : "Full screen"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          {isActive && (
            <button
              onClick={stopBrowser}
              className="p-1.5 rounded-md hover:bg-rose-950/60 text-neutral-400 hover:text-rose-400 transition-colors"
              title="Terminate browser process"
            >
              <Power size={14} />
            </button>
          )}
          <button
            onClick={closePanel}
            className="p-1.5 rounded-md hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
            title="Close browser panel"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* Navigation URL Bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-neutral-900 border-b border-neutral-800">
        <button
          onClick={reload}
          disabled={!isActive}
          className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 disabled:opacity-40 transition-colors"
          title="Reload page"
        >
          <RotateCw size={13} />
        </button>

        <form onSubmit={handleUrlSubmit} className="flex-1 flex items-center">
          <div className="relative w-full flex items-center">
            <div className="absolute left-2.5 text-neutral-500">
              <Globe size={13} />
            </div>
            <input
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="Enter URL to navigate (e.g. https://id.jobstreet.com)..."
              className="w-full pl-8 pr-8 py-1.5 text-xs bg-neutral-950 text-neutral-200 rounded border border-neutral-800 focus:outline-none focus:border-neutral-600 font-mono transition-colors"
            />
            <button
              type="submit"
              className="absolute right-1.5 p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200"
            >
              <ArrowRight size={13} />
            </button>
          </div>
        </form>

        <a
          href={currentUrl || "https://id.jobstreet.com"}
          target="_blank"
          rel="noreferrer"
          className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
          title="Open in default browser"
        >
          <ExternalLink size={13} />
        </a>
      </div>

      {/* Viewport / Interactive Screencast */}
      <div
        ref={containerRef}
        className="flex-1 relative bg-neutral-950 flex items-center justify-center overflow-hidden cursor-crosshair"
        onClick={() => setIsFocused(true)}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
      >
        {frameSrc ? (
          <img
            ref={imageRef}
            src={frameSrc}
            alt="Browser Live Stream"
            className="w-full h-full object-contain pointer-events-auto block"
            onMouseMove={handleMouseMove}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
            onContextMenu={(e) => e.preventDefault()}
            draggable={false}
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-neutral-500 gap-3 px-6 text-center">
            {isActive ? (
              <>
                <Loader2 className="animate-spin text-neutral-400" size={28} />
                <p className="text-xs text-neutral-400 font-medium">
                  Connecting to browser viewport...
                </p>
              </>
            ) : (
              <>
                <div className="w-12 h-12 rounded-full bg-neutral-800/80 flex items-center justify-center text-neutral-400 mb-1">
                  <ShieldCheck size={24} />
                </div>
                <p className="text-sm font-semibold text-neutral-200">
                  Browser Viewport Idle
                </p>
                <p className="text-xs text-neutral-400 max-w-sm">
                  Launch an interactive browser session to log in to Jobstreet, complete verification, or inspect live runs.
                </p>
                <button
                  onClick={() => navigate("https://id.jobstreet.com/id/oauth/login?returnUrl=%2F")}
                  className="mt-2 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
                >
                  Open Jobstreet Login
                </button>
              </>
            )}
          </div>
        )}

        {/* Focus indicator banner */}
        {isFocused && frameSrc && (
          <div className="absolute bottom-2 left-3 px-2 py-0.5 rounded bg-neutral-900/80 border border-neutral-700/60 text-[10px] text-neutral-300 backdrop-blur-xs pointer-events-none">
            Interactive: Keyboard & Mouse active
          </div>
        )}
      </div>

      {/* Footer info */}
      <div className="px-3.5 py-2 bg-neutral-950 border-t border-neutral-800 flex items-center justify-between text-[11px] text-neutral-400">
        <div className="flex items-center gap-1.5">
          <span className="text-neutral-500">Profile:</span>
          <span className="font-mono text-neutral-300">data/browser_profile</span>
        </div>
        <div className="flex items-center gap-2">
          <span>{viewportDims.width}x{viewportDims.height}</span>
          {lastFrameTime > 0 && (
            <span className="text-emerald-500 font-medium">Live</span>
          )}
        </div>
      </div>
    </aside>
  );
}
