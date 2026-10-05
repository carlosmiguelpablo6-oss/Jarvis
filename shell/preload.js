const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvis", {
  openDashboard: () => ipcRenderer.send("dashboard:open"),
  getSpherePosition: () => ipcRenderer.invoke("sphere:get-position"),
  moveSphere: (x, y) => ipcRenderer.send("sphere:move", x, y),
});