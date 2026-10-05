const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electron', {
  onScreenshotCaptured: (cb) => ipcRenderer.on('screenshot-captured', (_, b64) => cb(b64)),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
