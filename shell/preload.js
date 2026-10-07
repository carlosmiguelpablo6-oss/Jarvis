const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvis", {
  // sphere
  openDashboard: () => ipcRenderer.send("dashboard:open"),
  getSpherePosition: () => ipcRenderer.invoke("sphere:get-position"),
  moveSphere: (x, y) => ipcRenderer.send("sphere:move", x, y),
  onOrbState: (callback) =>
    ipcRenderer.on("orb:state", (_event, state) => callback(state)),

  // chat
  sendChat: (message) => ipcRenderer.invoke("chat:send", message),
  getHistory: () => ipcRenderer.invoke("chat:history"),
  
  // memory
  listFacts: () => ipcRenderer.invoke("facts:list"),
  addFact: (fact) => ipcRenderer.invoke("facts:add", fact),
  deleteFact: (id) => ipcRenderer.invoke("facts:delete", id),

  // tasks
  listTasks: () => ipcRenderer.invoke("tasks:list"),
  addTask: (title) => ipcRenderer.invoke("tasks:add", title),
  setTaskDone: (id, done) => ipcRenderer.invoke("tasks:set-done", id, done),
  deleteTask: (id) => ipcRenderer.invoke("tasks:delete", id),
});