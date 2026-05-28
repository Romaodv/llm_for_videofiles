const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("llmForfilesDesktop", {
  getRuntimeConfig() {
    return ipcRenderer.invoke("llm-forfiles:get-runtime-config");
  },
  pickVideo() {
    return ipcRenderer.invoke("llm-forfiles:pick-video");
  },
  pickFolder() {
    return ipcRenderer.invoke("llm-forfiles:pick-folder");
  },
});
