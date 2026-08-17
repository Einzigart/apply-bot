import { app, BrowserWindow, shell, nativeImage } from "electron";
import { spawn, ChildProcess } from "node:child_process";
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
    });
  } else {
    pythonProcess = spawn("uv", ["run", "python", "-m", "src.api.main", "--port", String(port), "--data-dir", DATA_DIR, "--logs-dir", LOGS_DIR], {
      cwd: PROJECT_ROOT,
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
    show: false,
    webPreferences: {
      preload: join(__dirname, isPackaged ? "preload.js" : "preload.ts"),
      contextIsolation: false,
      nodeIntegration: true,
    },
  });

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
    // Fallback if loading immediately fails on slow spawn
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
    if (process.platform === "darwin" && app.dock && existsSync(iconPath)) {
      try {
        app.dock.setIcon(iconPath);
      } catch {
        // ignore dock icon failure
      }
    }
    return createWindow();
  });

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
