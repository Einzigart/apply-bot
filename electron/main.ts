import { app, BrowserWindow, shell, nativeImage, Menu, dialog } from "electron";
import { spawn, spawnSync, ChildProcess } from "node:child_process";
import { join, dirname } from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import getPort from "get-port";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

app.name = "Apply Bot";
app.setName("Apply Bot");
process.title = "Apply Bot";

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.env.NODE_ENV === "development" && !process.env.PREVIEW;
const isPackaged = app.isPackaged;
const PROJECT_ROOT = existsSync(join(__dirname, "..", "src", "api", "main.py"))
  ? join(__dirname, "..")
  : join(__dirname, "../..");

// In development or preview (`bun run dev`, `bun run preview`): ALWAYS use repository data/
// In packaged production (.app / .exe): use user app data (~/Library/Application Support/Apply Bot)
const isDevOrPreview = !isPackaged || !!process.env.PREVIEW || process.env.NODE_ENV === "development";

const ROOT = process.env.APPLY_BOT_ROOT || (isDevOrPreview ? PROJECT_ROOT : app.getPath("userData"));
const DATA_DIR = process.env.APPLY_BOT_DATA_DIR || (
  isDevOrPreview ? join(PROJECT_ROOT, "data") : join(app.getPath("userData"), "data")
);
const LOGS_DIR = process.env.APPLY_BOT_LOGS_DIR || (
  isDevOrPreview ? join(PROJECT_ROOT, "logs") : join(app.getPath("userData"), "logs")
);
const iconPath = isPackaged
  ? join(process.resourcesPath || "", "app.asar", "assets", "icon.png")
  : join(__dirname, "assets", "icon.png");

async function startPythonBackend(port: number): Promise<void> {
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    APPLY_BOT_DATA_DIR: DATA_DIR,
    APPLY_BOT_LOGS_DIR: LOGS_DIR,
  };

  const isWin = process.platform === "win32";
  const binaryName = isWin ? "api-server.exe" : "api-server";
  const bundledBinaryPath = join(process.resourcesPath || "", "api-server", binaryName);
  if (isPackaged && existsSync(bundledBinaryPath)) {
    // In bundled release: launch bundled pyinstaller binary
    pythonProcess = spawn(bundledBinaryPath, ["--port", String(port), "--data-dir", DATA_DIR, "--logs-dir", LOGS_DIR], {
      cwd: ROOT,
      env,
      stdio: "inherit",
      windowsHide: true,
    });
  } else {
    pythonProcess = spawn("uv", ["run", "python", "-m", "src.api.main", "--port", String(port), "--data-dir", DATA_DIR, "--logs-dir", LOGS_DIR], {
      cwd: PROJECT_ROOT,
      env,
      stdio: "inherit",
      windowsHide: true,
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

async function createWindow() {
  const port = await getPort({ port: 5139 });
  await startPythonBackend(port);

  mainWindow = new BrowserWindow({
    title: "Apply Bot",
    width: 1240,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#ffffff",
    ...(existsSync(iconPath) ? { icon: iconPath } : {}),
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: { x: 16, y: 14 },
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, isPackaged ? "preload.js" : "dist/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.platform !== "darwin") {
    mainWindow.setMenu(null);
  }

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  // Open external links in real browser (http/https only)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        shell.openExternal(url);
      }
    } catch {
      // ignore invalid URLs
    }
    return { action: "deny" };
  });

  if (isDev) {
    // In dev: load Vite dev server
    await mainWindow.loadURL("http://localhost:5173");
  } else {
    // In production / preview: clear HTTP cache before loading to guarantee freshest bundle
    await mainWindow.webContents.session.clearCache();
    try {
      await mainWindow.loadURL(`http://127.0.0.1:${port}`);
    } catch {
      await new Promise((r) => setTimeout(r, 500));
      await mainWindow.loadURL(`http://127.0.0.1:${port}`);
    }
  }

  mainWindow.show();

  mainWindow.on("closed", () => {
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

  app.whenReady().then(() => {
    if (process.platform !== "darwin") {
      Menu.setApplicationMenu(null);
    }
    if (process.platform === "darwin" && app.dock && existsSync(iconPath)) {
      try {
        app.dock.setIcon(iconPath);
      } catch {
        // ignore dock icon failure
      }
    }
    return createWindow();
  }).catch((err) => {
    dialog.showErrorBox("Startup Error", `Apply Bot failed to start: ${err?.message || err}`);
    app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow().catch((err) => {
        dialog.showErrorBox("Startup Error", `Apply Bot failed to start: ${err?.message || err}`);
      });
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  const killPythonProcess = () => {
    if (!pythonProcess) return;
    try {
      if (process.platform === "win32" && pythonProcess.pid) {
        spawnSync("taskkill", ["/pid", String(pythonProcess.pid), "/T", "/F"], { windowsHide: true });
      } else {
        pythonProcess.kill("SIGTERM");
      }
    } catch {
      // ignore
    }
    pythonProcess = null;
  };

  app.on("before-quit", killPythonProcess);
  app.on("will-quit", killPythonProcess);
}
