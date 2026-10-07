const { app, BrowserWindow, screen, ipcMain } = require("electron");

const { Tray, Menu, nativeImage } = require("electron");
const { spawn, execSync} = require("child_process");
const path = require("path");
const fs = require("fs");

const BACKEND = "http://127.0.0.1:8000";
const SPHERE_SIZE = 140;
let sphereWindow = null;
let dashboardWindow = null;
let isQuitting = false;

let backendProcess = null;
let tray = null;

function startBackend() {
  const backendDir = path.join(__dirname, "..", "backend");
  const python = path.join(backendDir, ".venv", "Scripts", "python.exe");
  const logDir = path.join(__dirname, "..", "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const log = fs.openSync(path.join(logDir, "backend.log"), "a");

  backendProcess = spawn(
    python,
    ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: backendDir, windowsHide: true, stdio: ["ignore", log, log] }
  );
  backendProcess.on("exit", () => {
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess) return;
  try {
    // /T kills the whole process tree, /F forces it.
    execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: "ignore" });
  } catch {}
  backendProcess = null;
}

function createTray() {
  tray = new Tray(nativeImage.createFromPath(path.join(__dirname, "icon.png")));
  tray.setToolTip("Jarvis");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Dashboard", click: () => openDashboard() },
      { type: "separator" },
      { label: "Quit Jarvis", click: () => app.quit() },
    ])
  );
  tray.on("click", () => openDashboard());
}

function createSphereWindow() {
  const { workArea } = screen.getPrimaryDisplay();

  sphereWindow = new BrowserWindow({
    width: SPHERE_SIZE,
    height: SPHERE_SIZE,
    x: workArea.x + workArea.width - SPHERE_SIZE - 24,
    y: workArea.y + workArea.height - SPHERE_SIZE - 24,
    frame: false,
    transparent: true,
    resizable: false,
    hasShadow: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  sphereWindow.loadFile("sphere.html");
}

function createDashboardWindow() {
  dashboardWindow = new BrowserWindow({
    width: 900,
    height: 640,
    minWidth: 600,
    minHeight: 400,
    title: "Jarvis Dashboard",
    backgroundColor: "#0b1220",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  dashboardWindow.setMenuBarVisibility(false);
  dashboardWindow.loadFile("dashboard.html");
  dashboardWindow.once("ready-to-show", () => dashboardWindow.show());

  dashboardWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      dashboardWindow.hide();
    }
  });
}

function openDashboard() {
  if (!dashboardWindow) {
    createDashboardWindow();
    return;
  }
  if (dashboardWindow.isMinimized()) dashboardWindow.restore();
  dashboardWindow.show();
  dashboardWindow.focus();
}

function setOrb(state) {
  if (sphereWindow && !sphereWindow.isDestroyed()) {
    sphereWindow.webContents.send("orb:state", state);
  }
}

ipcMain.on("dashboard:open", openDashboard);

ipcMain.handle("sphere:get-position", () => sphereWindow.getPosition());

ipcMain.on("sphere:move", (_event, x, y) => {
  if (sphereWindow) {
    sphereWindow.setBounds({
      x: Math.round(x),
      y: Math.round(y),
      width: SPHERE_SIZE,
      height: SPHERE_SIZE,
    });
  }
});

ipcMain.handle("chat:send", async (_event, message) => {
  setOrb("thinking");
  try {
    const res = await fetch(`${BACKEND}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    setOrb("speaking");
    setTimeout(() => setOrb("idle"), 2000);
    return { ok: true, reply: data.reply };
  } catch (err) {
    setOrb("idle");
    return { ok: false, error: "Can't reach the Jarvis server. Is it running?" };
  }
});

ipcMain.handle("chat:history", async () => {
  try {
    const res = await fetch(`${BACKEND}/history`);
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
});

ipcMain.handle("facts:list", async () => {
  try {
    const res = await fetch(`${BACKEND}/facts`);
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
});

ipcMain.handle("facts:add", async (_event, fact) => {
  if (typeof fact !== "string" || !fact.trim()) return false;
  try {
    const res = await fetch(`${BACKEND}/facts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fact }),
    });
    return res.ok;
  } catch {
    return false;
  }
});

ipcMain.handle("facts:delete", async (_event, id) => {
  if (!Number.isInteger(id)) return false;
  try {
    const res = await fetch(`${BACKEND}/facts/${id}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
});

ipcMain.handle("tasks:list", async () => {
  try {
    const res = await fetch(`${BACKEND}/tasks?include_done=true`);
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
});

ipcMain.handle("tasks:add", async (_event, title) => {
  if (typeof title !== "string" || !title.trim()) return false;
  try {
    const res = await fetch(`${BACKEND}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    return res.ok;
  } catch {
    return false;
  }
});

ipcMain.handle("tasks:set-done", async (_event, id, done) => {
  if (!Number.isInteger(id) || typeof done !== "boolean") return false;
  try {
    const res = await fetch(`${BACKEND}/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done }),
    });
    return res.ok;
  } catch {
    return false;
  }
});

ipcMain.handle("tasks:delete", async (_event, id) => {
  if (!Number.isInteger(id)) return false;
  try {
    const res = await fetch(`${BACKEND}/tasks/${id}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});

const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => openDashboard());

  app.whenReady().then(() => {
    startBackend();
    createSphereWindow();
    createTray();
  });
}

app.on("window-all-closed", () => {
  app.quit();
});