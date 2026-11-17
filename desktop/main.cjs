// The Collaborative desktop app: a window showing the web UI (web/dist), plus the things a web
// page can't do: pick a .blend, move it to and from the server, and launch Blender into a room.
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { app, BrowserWindow, Notification, dialog, ipcMain, net, protocol, shell } = require('electron')

const { findBlender } = require('./lib/blender.cjs')
const files = require('./lib/files.cjs')
const { launch } = require('./lib/launch.cjs')
const { Settings, normalizeServerUrl } = require('./lib/settings.cjs')

// In a packaged app the UI and the add-on are copied into its resources folder.
const resources = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..')
const WEB_DIR = path.join(resources, 'web', 'dist')
const ADDON_DIR = path.join(resources, 'addon')
const LAUNCH_SCRIPT = path.join(__dirname, 'blender', 'launch.py')
const ROOM_NAME = /^[A-Za-z0-9_-]{1,64}$/

let settings
let window
// Files the user picked in a dialog, by a handle the page can hold. The page never names a
// path itself, so it can only ever upload something the user chose.
const picked = new Map()

// Served as app://collaborative/ rather than file://, so the page has a real origin for its
// content security policy and can't read other files by URL.
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } },
])

function serveUi() {
  protocol.handle('app', (request) => {
    const relative = decodeURIComponent(new URL(request.url).pathname)
    const target = path.normalize(path.join(WEB_DIR, relative === '/' ? 'index.html' : relative))
    if (!target.startsWith(WEB_DIR + path.sep)) return new Response('Not found', { status: 404 })
    return net.fetch(pathToFileURL(target).toString())
  })
}

function createWindow() {
  window = new BrowserWindow({
    width: 1240,
    height: 860,
    minWidth: 760,
    minHeight: 560,
    title: 'Collaborative',
    backgroundColor: '#f6f6f3',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  // The window only ever shows the app itself; a link to anywhere else opens in the browser.
  window.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('app://collaborative/')) event.preventDefault()
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })
  window.loadURL('app://collaborative/')
}

const publicSettings = () => ({
  serverUrl: settings.values.serverUrl,
  blenderPath: settings.values.blenderPath,
  detectedBlender: findBlender() ?? '',
})

function requireRoom(roomId) {
  if (typeof roomId !== 'string' || !ROOM_NAME.test(roomId)) throw new Error('That room name is not valid.')
  return roomId
}

function registerHandlers() {
  ipcMain.handle('settings:get', publicSettings)

  ipcMain.handle('settings:save', (_event, { serverUrl }) => {
    settings.setServerUrl(serverUrl)
    return publicSettings()
  })

  ipcMain.handle('pick:blend', async () => {
    const result = await dialog.showOpenDialog(window, {
      title: 'Choose the Blender file for this room',
      properties: ['openFile'],
      filters: [{ name: 'Blender files', extensions: ['blend'] }],
    })
    if (result.canceled || result.filePaths.length === 0) return null
    const filePath = result.filePaths[0]
    const id = crypto.randomUUID()
    picked.set(id, filePath)
    return { id, name: path.basename(filePath), size: fs.statSync(filePath).size }
  })

  // Blender's location is only ever set from this dialog, so the page can't point the app at
  // some other program to run.
  ipcMain.handle('pick:blender', async () => {
    const result = await dialog.showOpenDialog(window, { title: 'Choose Blender', properties: ['openFile'] })
    if (result.canceled || result.filePaths.length === 0) return null
    if (!findBlender({ chosen: result.filePaths[0] })) return null
    settings.setBlenderPath(result.filePaths[0])
    return result.filePaths[0]
  })

  ipcMain.handle('room:host-file', async (_event, { serverUrl, token, roomId, fileId }) => {
    const filePath = picked.get(fileId)
    if (!filePath) throw new Error('Choose the Blender file again.')
    const server = normalizeServerUrl(serverUrl)
    await files.upload({ serverUrl: server, token, roomId: requireRoom(roomId), filePath })
    settings.setHostFile(server, roomId, filePath)
    picked.delete(fileId)
  })

  ipcMain.handle('room:forget', (_event, roomId) => {
    settings.setHostFile(settings.values.serverUrl, requireRoom(roomId), null)
  })

  ipcMain.handle('room:launch', (event, request) =>
    launch(request, {
      settings,
      cacheDir: path.join(app.getPath('userData'), 'rooms'),
      launchScript: LAUNCH_SCRIPT,
      addonDir: ADDON_DIR,
      progress: (message) => event.sender.send('progress', message),
    }),
  )

  ipcMain.on('notify', (_event, { title, body }) => {
    if (Notification.isSupported()) new Notification({ title: String(title), body: String(body) }).show()
  })
}

app.whenReady().then(() => {
  settings = new Settings(app.getPath('userData'))
  serveUi()
  registerHandlers()
  createWindow()
  app.on('activate', () => BrowserWindow.getAllWindows().length === 0 && createWindow())
})

app.on('window-all-closed', () => process.platform !== 'darwin' && app.quit())
