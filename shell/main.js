const {
  app,
  BrowserWindow,
  screen,
  ipcMain,
  Tray,
  Menu,
  Notification,
  nativeImage,
} = require("electron");
const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const BACKEND = "http://127.0.0.1:8000";
const SPHERE_SIZE = 140;
let sphereWindow = null;
let dashboardWindow = null;
let isQuitting = false;
let backendProcess = null;
let tray = null;
let reminderTimer = null;

// Lets Windows show notifications while Jarvis runs from `npm start` or a shortcut.
app.setAppUserModelId(process.execPath);

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

  // Closing the dashboard hides it instead of destroying it,
  // so it reopens instantly and keeps its state.
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

// ---------- reminders: ask the backend every 30 seconds what is due ----------
async function checkReminders() {
  try {
    const res = await fetch(`${BACKEND}/reminders/claim`, { method: "POST" });
    if (!res.ok) return;
    const due = await res.json();
    for (const reminder of due) {
      const note = new Notification({
        title: "Jarvis reminder",
        body: reminder.text,
      });
      note.on("click", () => openDashboard());
      note.show();
      setOrb("speaking");
      setTimeout(() => setOrb("idle"), 5000);
    }
  } catch {
    // The backend may still be starting. Try again on the next tick.
  }
}

// ---------- daily briefing: the backend returns it only once per day ----------
async function checkDailyBriefing() {
  try {
    const res = await fetch(`${BACKEND}/briefing/auto`, { method: "POST" });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.text) return;
    const note = new Notification({
      title: "Jarvis daily briefing",
      body: "Your briefing is ready. Click to read it.",
    });
    note.on("click", () => openDashboard());
    note.show();
    setOrb("speaking");
    setTimeout(() => setOrb("idle"), 5000);
  } catch {
    // The backend may still be starting. A second attempt runs later.
  }
}

// ---------- window and chat messages from the pages ----------
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

// ---------- memory (facts) ----------
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

// ---------- tasks ----------
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

// ---------- notes ----------
ipcMain.handle("notes:list", async () => {
  try {
    const res = await fetch(`${BACKEND}/notes`);
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
});

ipcMain.handle("notes:add", async (_event, content) => {
  if (typeof content !== "string" || !content.trim()) return false;
  try {
    const res = await fetch(`${BACKEND}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    return res.ok;
  } catch {
    return false;
  }
});

ipcMain.handle("notes:delete", async (_event, id) => {
  if (!Number.isInteger(id)) return false;
  try {
    const res = await fetch(`${BACKEND}/notes/${id}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
});

// ---------- reminders ----------
ipcMain.handle("reminders:list", async () => {
  try {
    const res = await fetch(`${BACKEND}/reminders`);
    return res.ok ? await res.json() : [];
  } catch {
    return [];
  }
});

ipcMain.handle("reminders:add", async (_event, text, when) => {
  if (typeof text !== "string" || !text.trim()) {
    return { ok: false, error: "Write what to be reminded about." };
  }
  if (typeof when !== "string" || !when.trim()) {
    return { ok: false, error: "Write when, for example: tomorrow at 7 am." };
  }
  try {
    const res = await fetch(`${BACKEND}/reminders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, when }),
    });
    if (res.ok) return { ok: true };
    let error = "Could not add that reminder.";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") error = data.detail;
    } catch {}
    return { ok: false, error };
  } catch {
    return { ok: false, error: "Can't reach the Jarvis server." };
  }
});

ipcMain.handle("reminders:delete", async (_event, id) => {
  if (!Number.isInteger(id)) return false;
  try {
    const res = await fetch(`${BACKEND}/reminders/${id}`, { method: "DELETE" });
    return res.ok;
  } catch {
    return false;
  }
});

// ---------- app lifecycle ----------
app.on("before-quit", () => {
  isQuitting = true;
  if (reminderTimer) clearInterval(reminderTimer);
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
    reminderTimer = setInterval(checkReminders, 30000);
    setTimeout(checkReminders, 15000);
    // Wait a little so the backend and the network are ready, then try twice.
    setTimeout(checkDailyBriefing, 25000);
    setTimeout(checkDailyBriefing, 90000);
  });
}

app.on("window-all-closed", () => {
  app.quit();
});