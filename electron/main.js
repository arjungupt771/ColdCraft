const { app, BrowserWindow, globalShortcut, ipcMain, screen, desktopCapturer } = require('electron')
const path = require('path')
const isDev = process.env.NODE_ENV !== 'production'

function createWindow() {
  const win = new BrowserWindow({
    width: 1100, height: 780, minWidth: 860, minHeight: 600,
    backgroundColor: '#0c0e14',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  })
  isDev ? win.loadURL('http://localhost:5173') : win.loadFile(path.join(__dirname, '../dist/index.html'))
  return win
}

app.whenReady().then(() => {
  const win = createWindow()

  // Global hotkey: Ctrl+Shift+S — triggers screenshot capture flow in renderer
  globalShortcut.register('CommandOrControl+Shift+S', async () => {
    win.focus()
    // Capture all screens
    const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 1920, height: 1080 } })
    if (sources.length > 0) {
      const png = sources[0].thumbnail.toPNG()
      const b64 = png.toString('base64')
      win.webContents.send('screenshot-captured', b64)
    }
  })

  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})

app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })

ipcMain.handle('open-external', (_, url) => {
  require('electron').shell.openExternal(url)
})
