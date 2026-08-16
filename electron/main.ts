import { app, BrowserWindow, shell } from "electron";
import { spawn, ChildProcess } from "node:child_process";
import { join } from "node:path";
import getPort from "get-port";

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.env.NODE_ENV === "development" || !app.isPackaged;
const ROOT = join(__dirname, "..");

async function startPythonBackend(port: number): Promise<void> {
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
  };

  if (isDev) {
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

async function createWindow() {
  const port = await getPort({ port: 5139 });
  await startPythonBackend(port);

  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#0f172a", // matches Notion-style dark sidebar
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: { x: 16, y: 16 },
    show: false,
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
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
