// The app's own settings, in one JSON file in its user-data folder: which server to use, where
// Blender is, and where each hosted room's project file lives on this computer.
const fs = require('node:fs')
const path = require('node:path')

const DEFAULTS = { serverUrl: 'http://localhost:8000', blenderPath: '', hostFiles: {} }

function normalizeServerUrl(value) {
  const url = new URL(String(value).trim())
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('The server address must start with http:// or https://')
  }
  return url.origin
}

class Settings {
  constructor(dir) {
    this.file = path.join(dir, 'settings.json')
    try {
      this.values = { ...DEFAULTS, ...JSON.parse(fs.readFileSync(this.file, 'utf8')) }
    } catch {
      this.values = { ...DEFAULTS } // first run, or an unreadable file: start from the defaults
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.file), { recursive: true })
    // Written beside the file, then renamed, so a crash can't leave half a settings file.
    fs.writeFileSync(`${this.file}.tmp`, JSON.stringify(this.values, null, 2))
    fs.renameSync(`${this.file}.tmp`, this.file)
  }

  setServerUrl(value) {
    this.values.serverUrl = normalizeServerUrl(value)
    this.save()
  }

  setBlenderPath(value) {
    this.values.blenderPath = value
    this.save()
  }

  // A room name only means something on one server, so the key carries both.
  static roomKey(serverUrl, roomId) {
    return `${normalizeServerUrl(serverUrl)}|${roomId}`
  }

  hostFile(serverUrl, roomId) {
    return this.values.hostFiles[Settings.roomKey(serverUrl, roomId)] ?? null
  }

  setHostFile(serverUrl, roomId, filePath) {
    const key = Settings.roomKey(serverUrl, roomId)
    if (filePath) this.values.hostFiles[key] = filePath
    else delete this.values.hostFiles[key]
    this.save()
  }
}

module.exports = { Settings, normalizeServerUrl }
