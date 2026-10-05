const { app, BrowserWindow, screen } = require("electron");

const SPHERE_SIZE = 140;
let sphereWindow = null;

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
  });

  sphereWindow.loadFile("sphere.html");
}

app.whenReady().then(createSphereWindow);

app.on("window-all-closed", () => {
  app.quit();
});