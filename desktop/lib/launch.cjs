// Launch Blender into a room: get the right file in place, then start Blender on it.
//
// The host opens their own file, the one they chose when creating the room, so their saves
// land where they expect; if it has changed since the server last saw it, it's uploaded first
// so everyone starts from the same thing. Everyone else opens a copy downloaded into the app's
// own folder, fetched again whenever it differs from the server's.
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')

const { findBlender, launchCommand } = require('./blender.cjs')
const files = require('./files.cjs')
const { normalizeServerUrl } = require('./settings.cjs')

const ROOM_NAME = /^[A-Za-z0-9_-]{1,64}$/
const ROLES = ['owner', 'editor', 'viewer']
const HASH = /^[0-9a-f]{64}$/

/** Check everything the page sent before any of it reaches the file system or a process. */
function checked(request) {
  const { token, username, roomId, role, fileHash, fileName } = request
  if (!ROOM_NAME.test(roomId)) throw new Error('That room name is not valid.')
  if (!ROLES.includes(role)) throw new Error('That role is not valid.')
  if (!HASH.test(fileHash)) throw new Error('This room has no project file yet.')
  if (typeof token !== 'string' || !token || typeof username !== 'string') throw new Error('Log in again.')
  return {
    serverUrl: normalizeServerUrl(request.serverUrl),
    token,
    username,
    roomId,
    role,
    fileHash,
    fileName: files.safeName(fileName),
  }
}

async function prepareFile(request, { settings, cacheDir, progress }) {
  const { serverUrl, token, roomId, role, fileHash, fileName } = request
  const own = role === 'owner' ? settings.hostFile(serverUrl, roomId) : null
  if (own && fs.existsSync(own)) {
    if ((await files.sha256(own)) !== fileHash) {
      progress('Sharing your latest file with the room…')
      await files.upload({ serverUrl, token, roomId, filePath: own })
    }
    return { filePath: own, trusted: true }
  }
  const target = path.join(cacheDir, new URL(serverUrl).host.replace(/[^A-Za-z0-9.-]/g, '_'), roomId, fileName)
  const current = fs.existsSync(target) && (await files.sha256(target)) === fileHash
  if (!current) {
    progress('Downloading the project file…')
    await files.download({ serverUrl, token, roomId, target, expectedHash: fileHash })
  }
  return { filePath: target, trusted: false }
}

function start({ command, args, env }) {
  return new Promise((resolve, reject) => {
    // Detached and unwatched: Blender is the user's own program and outlives this app.
    const child = spawn(command, args, { env: { ...process.env, ...env }, detached: true, stdio: 'ignore' })
    child.once('error', (error) => reject(new Error(`Blender couldn't be started: ${error.message}`)))
    child.once('spawn', () => {
      child.unref()
      resolve()
    })
  })
}

async function launch(rawRequest, { settings, cacheDir, launchScript, addonDir, progress = () => {} }) {
  const request = checked(rawRequest)
  const blender = findBlender({ chosen: settings.values.blenderPath })
  if (!blender) throw new Error("Blender wasn't found. Choose it in Settings.")
  const { filePath, trusted } = await prepareFile(request, { settings, cacheDir, progress })
  progress('Opening Blender…')
  await start(launchCommand({ ...request, blender, filePath, trusted, launchScript, addonDir }))
}

module.exports = { launch, checked, prepareFile }
