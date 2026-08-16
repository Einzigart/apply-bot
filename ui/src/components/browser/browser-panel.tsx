import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  X,
  RotateCw,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Power,
  Maximize2,
  Minimize2,
  ShieldCheck,
  Globe,
  Loader2,
  GripVertical,
  Plus,
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
    goBack,
    goForward,
    reload,
    resizeViewport,
    sendMouseEvent,
    sendWheelEvent,
    sendKeyEvent,
    setOnFrame,
  } = useBrowser();

  const isElectron = typeof window !== "undefined" && !!(window as any).electronAPI?.isElectron;
  const electronAPI = (window as any)?.electronAPI;

  const [inputUrl, setInputUrl] = useState(currentUrl || "");
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [panelWidth, setPanelWidth] = useState<number>(680);
  const [isResizing, setIsResizing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [lastFrameTime, setLastFrameTime] = useState<number>(0);
  const [viewportDims, setViewportDims] = useState<{ width: number; height: number }>({ width: 1280, height: 800 });
  const [electronTitle, setElectronTitle] = useState("");
  const [electronUrl, setElectronUrl] = useState("");

  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const resizeTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    if (isElectron && electronUrl) {
      setInputUrl(electronUrl);
    } else {
      setInputUrl(currentUrl);
    }
  }, [currentUrl, electronUrl, isElectron]);

  // Native Electron WebContentsView listener & lifecycle
  useEffect(() => {
    if (!isElectron || !electronAPI) return;

    const cleanup = electronAPI.onBrowserViewState?.((state: any) => {
      if (state.url) setElectronUrl(state.url);
      if (state.title) setElectronTitle(state.title);
    });

    return () => {
      cleanup?.();
    };
  }, [isElectron, electronAPI]);

  // Sync Electron WebContentsView bounds
  const syncElectronBounds = useCallback(() => {
    if (!isElectron || !electronAPI || !containerRef.current || !isOpen) return;
    const rect = containerRef.current.getBoundingClientRect();
    electronAPI.updateBrowserViewBounds({
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    });
  }, [isElectron, electronAPI, isOpen]);

  useEffect(() => {
    if (!isElectron || !isOpen) return;
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const targetUrl = currentUrl || "https://id.jobstreet.com/id/oauth/login?returnUrl=%2F";
      electronAPI?.openBrowserView(targetUrl, {
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      });
    }
  }, [isOpen, isElectron]);

  useEffect(() => {
    if (isElectron && isOpen) {
      syncElectronBounds();
    }
  }, [panelWidth, isFullscreen, isOpen, isElectron, syncElectronBounds]);

  const handleClose = useCallback(() => {
    if (isElectron && electronAPI) {
      try {
        electronAPI.closeBrowserView();
      } catch (e) {
        console.error("Error closing browser view:", e);
      }
    }
    closePanel();
  }, [isElectron, electronAPI, closePanel]);

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

    if (isElectron) {
      syncElectronBounds();
      return;
    }

    if (w > 100 && h > 100 && (w !== viewportDims.width || h !== viewportDims.height)) {
      setViewportDims({ width: w, height: h });
      if (resizeTimeoutRef.current) {
        window.clearTimeout(resizeTimeoutRef.current);
      }
      resizeTimeoutRef.current = window.setTimeout(() => {
        resizeViewport(w, h);
      }, 100);
    }
  }, [viewportDims, resizeViewport, isElectron, syncElectronBounds]);

  useEffect(() => {
    if (isOpen) {
      updateViewportSize();
    }
  }, [panelWidth, isFullscreen, isOpen, updateViewportSize]);

  // Listen to window resize as well
  useEffect(() => {
    window.addEventListener("resize", updateViewportSize);
    return () => window.removeEventListener("resize", updateViewportSize);
  }, [updateViewportSize]);

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUrl.trim()) return;
    let url = inputUrl.trim();
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = "https://" + url;
    }
    if (isElectron && electronAPI) {
      electronAPI.navigateBrowserView(url);
    } else {
      navigate(url);
    }
  };

  const handleGoBack = () => {
    if (isElectron && electronAPI) {
      electronAPI.goBackBrowserView();
    } else {
      goBack();
    }
  };

  const handleGoForward = () => {
    if (isElectron && electronAPI) {
      electronAPI.goForwardBrowserView();
    } else {
      goForward();
    }
  };

  const handleReload = () => {
    if (isElectron && electronAPI) {
      electronAPI.reloadBrowserView();
    } else {
      reload();
    }
  };

  // Precise coordinates mapping from container/img element to viewport (web mode fallback)
  const getCdpCoords = (e: React.MouseEvent<HTMLElement>) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    const targetW = viewportDims.width || 680;
    const targetH = viewportDims.height || 750;
    const scaleX = targetW / rect.width;
    const scaleY = targetH / rect.height;
    const x = Math.max(0, Math.min(targetW, (e.clientX - rect.left) * scaleX));
    const y = Math.max(0, Math.min(targetH, (e.clientY - rect.top) * scaleY));
    return { x: Math.round(x), y: Math.round(y) };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLElement>) => {
    if (isElectron) return;
    const { x, y } = getCdpCoords(e);
    sendMouseEvent("mouseMoved", x, y);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLElement>) => {
    if (isElectron) return;
    containerRef.current?.focus();
    setIsFocused(true);
    const { x, y } = getCdpCoords(e);
    const button = e.button === 2 ? "right" : e.button === 1 ? "middle" : "left";
    sendMouseEvent("mousePressed", x, y, button, e.detail || 1);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLElement>) => {
    if (isElectron) return;
    const { x, y } = getCdpCoords(e);
    const button = e.button === 2 ? "right" : e.button === 1 ? "middle" : "left";
    sendMouseEvent("mouseReleased", x, y, button, 1);
  };

  const handleWheel = (e: React.WheelEvent<HTMLElement>) => {
    if (isElectron) return;
    const { x, y } = getCdpCoords(e);
    sendWheelEvent(x, y, e.deltaX, e.deltaY);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isElectron) return;
    if (e.key === "Tab") {
      e.preventDefault();
    }
    const isPrintable = e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey;
    sendKeyEvent("keyDown", e.key, e.code, isPrintable ? e.key : undefined, e.keyCode);
  };

  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (isElectron) return;
    sendKeyEvent("keyUp", e.key, e.code, undefined, e.keyCode);
  };

  // Extract clean domain / hostname for ChatGPT-style topbar
  const getDisplayDomain = () => {
    const activeUrl = (isElectron ? electronUrl : currentUrl) || "";
    try {
      if (!activeUrl) return "jobstreet.com";
      const u = new URL(activeUrl);
      return u.hostname;
    } catch {
      return activeUrl || "jobstreet.com";
    }
  };

  if (!isOpen) return null;

  return (
    <aside
      style={isFullscreen ? { width: "100vw", left: 0 } : { width: `${panelWidth}px` }}
      className="fixed top-0 right-0 h-screen z-50 flex flex-col bg-[#212121] border-l border-[#2f2f2f] shadow-2xl transition-[width] duration-75 select-none text-neutral-200"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
    >
      {/* Draggable Left Resize Handle */}
      {!isFullscreen && (
        <div
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizing(true);
          }}
          className="absolute left-0 top-0 bottom-0 w-3 -translate-x-1/2 cursor-ew-resize hover:bg-neutral-600/40 z-50 flex items-center justify-center group select-none"
          title="Drag to resize browser width"
        >
          <div className="w-1 h-8 rounded-full bg-neutral-600/60 group-hover:bg-neutral-400 group-hover:h-12 transition-all flex items-center justify-center">
            <GripVertical size={8} className="text-white opacity-0 group-hover:opacity-100" />
          </div>
        </div>
      )}

      {/* ChatGPT-style Tab Bar */}
      <div className="flex items-center justify-between px-3 pt-2 pb-1.5 bg-[#171717] border-b border-[#2a2a2a] titlebar-no-drag select-none z-20">
        <div className="flex items-center gap-1 overflow-hidden">
          {/* Active Tab Pill */}
          <div className="flex items-center gap-2 px-3 py-1 bg-[#212121] border border-[#333] rounded-lg text-xs font-normal text-neutral-200 max-w-[280px] shadow-xs">
            <Globe size={13} className="text-neutral-400 shrink-0" />
            <span className="truncate">{(isElectron ? electronTitle : currentTitle) || getDisplayDomain()}</span>
            <button
              type="button"
              onClick={handleClose}
              className="p-0.5 ml-1 rounded hover:bg-neutral-700 text-neutral-400 hover:text-neutral-200 cursor-pointer pointer-events-auto"
            >
              <X size={11} />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-0.5 text-neutral-400">
          <button
            type="button"
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-md hover:bg-neutral-800 hover:text-neutral-200 transition-colors cursor-pointer pointer-events-auto"
            title={isFullscreen ? "Restore window" : "Full screen"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          {!isElectron && isActive && (
            <button
              type="button"
              onClick={stopBrowser}
              className="p-1.5 rounded-md hover:bg-rose-950/60 hover:text-rose-400 transition-colors cursor-pointer pointer-events-auto"
              title="Terminate browser process"
            >
              <Power size={14} />
            </button>
          )}
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-md hover:bg-neutral-800 hover:text-neutral-200 transition-colors cursor-pointer pointer-events-auto"
            title="Close browser panel"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* ChatGPT-style Navigation & Centered URL Bar */}
      <div className="flex items-center gap-1.5 px-3 py-2 bg-[#212121] border-b border-[#2e2e2e] titlebar-no-drag select-none z-20">
        <button
          type="button"
          onClick={handleGoBack}
          className="p-1.5 rounded-md hover:bg-[#2f2f2f] text-neutral-400 hover:text-neutral-200 disabled:opacity-30 transition-colors cursor-pointer pointer-events-auto"
          title="Back"
        >
          <ArrowLeft size={14} />
        </button>

        <button
          type="button"
          onClick={handleGoForward}
          className="p-1.5 rounded-md hover:bg-[#2f2f2f] text-neutral-400 hover:text-neutral-200 disabled:opacity-30 transition-colors cursor-pointer pointer-events-auto"
          title="Forward"
        >
          <ArrowRight size={14} />
        </button>

        <button
          type="button"
          onClick={handleReload}
          className="p-1.5 rounded-md hover:bg-[#2f2f2f] text-neutral-400 hover:text-neutral-200 disabled:opacity-30 transition-colors cursor-pointer pointer-events-auto"
          title="Reload page"
        >
          <RotateCw size={13} />
        </button>

        {/* URL Pill / Search Bar */}
        <form onSubmit={handleUrlSubmit} className="flex-1 flex items-center mx-1 pointer-events-auto">
          <div className="relative w-full flex items-center justify-center">
            <input
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="Search or enter web address..."
              className="w-full text-center px-4 py-1 text-xs bg-[#171717] hover:bg-[#1a1a1a] focus:bg-[#171717] focus:text-left text-neutral-300 rounded-full border border-[#333] focus:outline-none focus:border-neutral-500 font-sans transition-all"
            />
          </div>
        </form>

        <a
          href={(isElectron ? electronUrl : currentUrl) || "https://id.jobstreet.com"}
          target="_blank"
          rel="noreferrer"
          className="p-1.5 rounded-md hover:bg-[#2f2f2f] text-neutral-400 hover:text-neutral-200 transition-colors cursor-pointer pointer-events-auto"
          title="Open in external browser"
        >
          <ExternalLink size={13} />
        </a>
      </div>

      {/* Viewport / Native WebContentsView Mount Area */}
      <div
        ref={containerRef}
        className="flex-1 relative bg-[#171717] flex items-stretch justify-stretch overflow-hidden cursor-default"
        onClick={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
        onContextMenu={(e) => e.preventDefault()}
        tabIndex={0}
      >
        {isElectron ? (
          <div className="w-full h-full bg-[#ffffff]" />
        ) : frameSrc ? (
          <img
            ref={imageRef}
            src={frameSrc}
            alt="Browser Live Stream"
            className="w-full h-full object-fill pointer-events-none block"
            draggable={false}
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-neutral-500 gap-3 px-6 text-center w-full h-full">
            {isActive ? (
              <>
                <Loader2 className="animate-spin text-neutral-400" size={28} />
                <p className="text-xs text-neutral-400 font-medium">
                  Connecting to browser viewport...
                </p>
              </>
            ) : (
              <>
                <div className="w-12 h-12 rounded-full bg-neutral-800 flex items-center justify-center text-neutral-400 mb-1">
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
                  className="mt-2 px-3.5 py-1.5 rounded-md bg-white text-black hover:bg-neutral-200 text-xs font-medium transition-colors"
                >
                  Open Jobstreet Login
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer info */}
      <div className="px-3.5 py-1.5 bg-[#171717] border-t border-[#2a2a2a] flex items-center justify-between text-[11px] text-neutral-400">
        <div className="flex items-center gap-1.5">
          <span className="text-neutral-500">{isElectron ? "Engine:" : "Profile:"}</span>
          <span className="font-mono text-neutral-300">{isElectron ? "Native Chromium (WebContentsView)" : "data/browser_profile"}</span>
        </div>
        <div className="flex items-center gap-2">
          {isElectron ? (
            <span className="text-emerald-500 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Native 60fps
            </span>
          ) : lastFrameTime > 0 ? (
            <span className="text-emerald-500 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
