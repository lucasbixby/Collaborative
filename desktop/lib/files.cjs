// Moving a room's project file between this computer and the server.
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const { pipeline } = require('node:stream/promises')
const { Readable } = require('node:stream')

async function sha256(filePath) {
  const hash = crypto.createHash('sha256')
  await pipeline(fs.createReadStream(filePath), hash)
  return hash.digest('hex')
}

const fileUrl = (serverUrl, roomId) => `${serverUrl}/api/rooms/${encodeURIComponent(roomId)}/file`

async function failure(response) {
  const body = await response.json().catch(() => null)
  const detail = typeof body?.detail === 'string' ? body.detail : `the server answered ${response.status}`
  return new Error(detail.charAt(0).toUpperCase() + detail.slice(1))
}

/** Upload the file at `filePath` as the room's project file. */
async function upload({ serverUrl, token, roomId, filePath }) {
  const response = await fetch(`${fileUrl(serverUrl, roomId)}?name=${encodeURIComponent(path.basename(filePath))}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream' },
    body: await fs.openAsBlob(filePath), // read from disk as it's sent, not loaded whole
  })
  if (!response.ok) throw await failure(response)
  return response.json()
}

/**
 * Download the room's project file to `target`, checking it is the content the server said.
 * Written beside its final place and renamed, so a failed download never leaves a broken file
 * where Blender would open it.
 */
async function download({ serverUrl, token, roomId, target, expectedHash }) {
  const response = await fetch(fileUrl(serverUrl, roomId), { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) throw await failure(response)
  await fs.promises.mkdir(path.dirname(target), { recursive: true })
  const partial = `${target}.part`
  try {
    await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(partial))
    if ((await sha256(partial)) !== expectedHash) {
      throw new Error("The downloaded file doesn't match the room's. Try again.")
    }
    await fs.promises.rename(partial, target)
  } catch (error) {
    await fs.promises.rm(partial, { force: true })
    throw error
  }
}

/** A file name from the server, reduced to something safe to create inside our own folder. */
function safeName(name) {
  const base = String(name).split(/[\\/]/).pop().replace(/[^A-Za-z0-9 ._()-]/g, '_').replace(/^\.+/, '')
  return base.toLowerCase().endsWith('.blend') && base.length > 6 ? base : 'project.blend'
}

module.exports = { sha256, upload, download, safeName }
