const { app, BrowserWindow, screen, ipcMain } = require("electron");
const path = require("path");

const SPHERE_SIZE = 140;
let sphereWindow = null;
let dashboardWindow = null;
let isQuitting = false;

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

app.on("before-quit", () => {
  isQuitting = true;
});

app.whenReady().then(createSphereWindow);

app.on("window-all-closed", () => {
  app.quit();
});