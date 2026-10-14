const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nekoDesktop", {
  openDashboard: () => ipcRenderer.send("neko:open-dashboard"),
  enablePet: () => ipcRenderer.invoke("neko:enable-pet"),
  setInteractive: (enabled) => ipcRenderer.invoke("neko:set-interactive", Boolean(enabled)),
  hidePet: () => ipcRenderer.invoke("neko:hide-pet"),
  exitApp: () => ipcRenderer.send("neko:exit-app"),
  openFocusBrowser: (url) => ipcRenderer.invoke("neko:open-focus-browser", String(url || "")),
  focusReaction: (message) => ipcRenderer.send("neko:focus-reaction", String(message || "")),
  onFocusReaction: (callback) => {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on("neko:focus-reaction", listener);
    return () => ipcRenderer.removeListener("neko:focus-reaction", listener);
  },
  onInteractionChange: (callback) => {
    const listener = (_event, enabled) => callback(enabled);
    ipcRenderer.on("neko:interaction-change", listener);
    return () => ipcRenderer.removeListener("neko:interaction-change", listener);
  },
});
