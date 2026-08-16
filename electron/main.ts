import { app, BrowserWindow, shell } from "electron";
import { spawn, ChildProcess } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import getPort from "get-port";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.env.NODE_ENV === "development" && !process.env.PREVIEW;
const isPackaged = app.isPackaged;
const ROOT = join(__dirname, "..");

async function startPythonBackend(port: number): Promise<void> {
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
  };

  if (!isPackaged) {
    pythonProcess = spawn("uv", ["run", "python", "-m", "src.api.main", "--port", String(port)], {
      cwd: ROOT,
      env,
      stdio: "inherit",
    });
  } else {
    // In bundled release: launch bundled pyinstaller binary
    const binaryPath = join(process.resourcesPath, "api-server", "api-server");
    pythonProcess = spawn(binaryPath, ["--port", String(port)], {
      cwd: ROOT,
      env,
      stdio: "inherit",
    });
  }

  // Poll until FastAPI server responds
  const url = `http://127.0.0.1:${port}/api/dashboard`;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // waiting
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("Python backend failed to start within 15 seconds.");
}

import { app, BrowserWindow, WebContentsView, shell, ipcMain, session } from "electron";
import { spawn, ChildProcess } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import getPort from "get-port";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let browserView: WebContentsView | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.env.NODE_ENV === "development" && !process.env.PREVIEW;
const isPackaged = app.isPackaged;
const ROOT = join(__dirname, "..");

async function startPythonBackend(port: number): Promise<void> {
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
  };

  if (!isPackaged) {
    pythonProcess = spawn("uv", ["run", "python", "-m", "src.api.main", "--port", String(port)], {
      cwd: ROOT,
      env,
      stdio: "inherit",
    });
  } else {
    // In bundled release: launch bundled pyinstaller binary
    const binaryPath = join(process.resourcesPath, "api-server", "api-server");
    pythonProcess = spawn(binaryPath, ["--port", String(port)], {
      cwd: ROOT,
      env,
      stdio: "inherit",
    });
  }

  // Poll until FastAPI server responds
  const url = `http://127.0.0.1:${port}/api/dashboard`;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // waiting
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("Python backend failed to start within 15 seconds.");
}

function sendBrowserViewState() {
  if (!browserView || !mainWindow || mainWindow.isDestroyed()) return;
  const wc = browserView.webContents;
  try {
    mainWindow.webContents.send("browser-view:state", {
      url: wc.getURL(),
      title: wc.getTitle(),
      canGoBack: wc.canGoBack(),
      canGoForward: wc.canGoForward(),
      isLoading: wc.isLoading(),
    });
  } catch {}
}

function setupBrowserViewIPC() {
  ipcMain.on("browser-view:open", (_, { url, bounds }) => {
    if (!mainWindow) return;

    if (!browserView) {
      // Use persistent partition for Jobstreet auth cookies & sessions
      const persistSession = session.fromPartition("persist:jobstreet-profile");
      
      // Set realistic Chrome desktop user agent
      persistSession.setUserAgent(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
      );

      browserView = new WebContentsView({
        webPreferences: {
          session: persistSession,
          contextIsolation: true,
          nodeIntegration: false,
        },
      });

      mainWindow.contentView.addChildView(browserView);

      const wc = browserView.webContents;
      wc.on("did-navigate", sendBrowserViewState);
      wc.on("did-navigate-in-page", sendBrowserViewState);
      wc.on("page-title-updated", sendBrowserViewState);
      wc.on("did-start-loading", sendBrowserViewState);
      wc.on("did-stop-loading", sendBrowserViewState);

      // Allow popups/new-window to load in the same view or open safely
      wc.setWindowOpenHandler(({ url: targetUrl }) => {
        if (targetUrl.includes("jobstreet") || targetUrl.includes("seek") || targetUrl.includes("google") || targetUrl.includes("accounts")) {
          wc.loadURL(targetUrl);
          return { action: "deny" };
        }
        shell.openExternal(targetUrl);
        return { action: "deny" };
      });
    }

    if (bounds) {
      browserView.setBounds({
        x: Math.round(bounds.x),
        y: Math.round(bounds.y),
        width: Math.max(100, Math.round(bounds.width)),
        height: Math.max(100, Math.round(bounds.height)),
      });
    }

    if (url) {
      browserView.webContents.loadURL(url);
    }
  });

  ipcMain.on("browser-view:bounds", (_, bounds) => {
    if (browserView && bounds) {
      browserView.setBounds({
        x: Math.round(bounds.x),
        y: Math.round(bounds.y),
        width: Math.max(100, Math.round(bounds.width)),
        height: Math.max(100, Math.round(bounds.height)),
      });
    }
  });

  ipcMain.on("browser-view:navigate", (_, url) => {
    if (browserView && url) {
      browserView.webContents.loadURL(url);
    }
  });

  ipcMain.on("browser-view:go-back", () => {
    if (browserView && browserView.webContents.canGoBack()) {
      browserView.webContents.goBack();
    }
  });

  ipcMain.on("browser-view:go-forward", () => {
    if (browserView && browserView.webContents.canGoForward()) {
      browserView.webContents.goForward();
    }
  });

  ipcMain.on("browser-view:reload", () => {
    if (browserView) {
      browserView.webContents.reload();
    }
  });

  ipcMain.on("browser-view:close", () => {
    if (browserView && mainWindow) {
      mainWindow.contentView.removeChildView(browserView);
      (browserView.webContents as any).destroy?.();
      browserView = null;
    }
  });
}

async function createWindow() {
  const port = await getPort({ port: 5139 });
  await startPythonBackend(port);

  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#ffffff",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: { x: 16, y: 14 },
    show: false,
    webPreferences: {
      preload: join(__dirname, "preload.ts"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  setupBrowserViewIPC();

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  // Open external links in real browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev) {
    // In dev: load Vite dev server
    await mainWindow.loadURL("http://localhost:5173");
  } else {
    // In production: load from FastAPI which serves dist/
    await mainWindow.loadURL(`http://127.0.0.1:${port}`);
  }

  mainWindow.on("closed", () => {
    if (browserView && mainWindow) {
      mainWindow.contentView.removeChildView(browserView);
      browserView = null;
    }
    mainWindow = null;
  });
}

const singleInstanceLock = app.requestSingleInstanceLock();
if (!singleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    if (pythonProcess) {
      try {
        pythonProcess.kill("SIGTERM");
      } catch {
        // ignore
      }
      pythonProcess = null;
    }
  });
}
