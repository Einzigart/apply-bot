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
const ROOT = process.env.APPLY_BOT_ROOT || (
  isPackaged
    ? app.getPath("userData")
    : (existsSync(join(__dirname, "..", "src", "api", "main.py"))
        ? join(__dirname, "..")
        : join(__dirname, "../.."))
);
const DATA_DIR = process.env.APPLY_BOT_DATA_DIR || (
  isPackaged ? join(app.getPath("userData"), "data") : join(ROOT, "data")
);
const LOGS_DIR = process.env.APPLY_BOT_LOGS_DIR || (
  isPackaged ? join(app.getPath("userData"), "logs") : join(ROOT, "logs")
);
const iconPath = join(__dirname, "assets", "icon.png");

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
    pythonProcess = spawn(bundledBinaryPath, ["--port", String(port)], {
      cwd: ROOT,
      env,
      stdio: "inherit",
    });
  } else {
    pythonProcess = spawn("uv", ["run", "python", "-m", "src.api.main", "--port", String(port)], {
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
    icon: iconPath,
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
    await mainWindow.loadURL(`http://127.0.0.1:${port}`);
  }

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
    if (process.platform === "darwin" && app.dock) {
      app.dock.setIcon(iconPath);
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
