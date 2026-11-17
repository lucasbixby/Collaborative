// Finding Blender on this computer, and working out how to start it inside a room.
const fs = require('node:fs')
const path = require('node:path')

const MAC_APP = '/Applications/Blender.app'
const MAC_BINARY = 'Contents/MacOS/Blender'

/** The Blender to run: the one chosen in Settings, or the usual install location. */
function findBlender({ chosen = '', platform = process.platform, env = process.env, exists = fs.existsSync } = {}) {
  if (chosen) {
    // Picking "Blender.app" in a macOS dialog gives the bundle; the program is inside it.
    const candidate = chosen.endsWith('.app') ? path.join(chosen, MAC_BINARY) : chosen
    return exists(candidate) ? candidate : null
  }
  const candidates = []
  if (platform === 'darwin') {
    candidates.push(path.join(MAC_APP, MAC_BINARY), path.join(env.HOME ?? '', MAC_APP, MAC_BINARY))
  } else if (platform === 'win32') {
    const root = path.win32.join(env.ProgramFiles ?? 'C:\\Program Files', 'Blender Foundation')
    let versions = []
    try {
      versions = fs.readdirSync(root).sort().reverse() // "Blender 5.2" before "Blender 4.5"
    } catch {
      // not installed there
    }
    candidates.push(...versions.map((folder) => path.win32.join(root, folder, 'blender.exe')))
  } else {
    const onPath = (env.PATH ?? '').split(path.delimiter).map((dir) => path.join(dir, 'blender'))
    candidates.push(...onPath, '/snap/bin/blender')
  }
  return candidates.find((candidate) => candidate && exists(candidate)) ?? null
}

/** The server's address as the add-on's socket wants it: http -> ws, https -> wss. */
function socketUrl(serverUrl) {
  return serverUrl.replace(/^http/, 'ws')
}

/**
 * The command that opens `filePath` in Blender, in the room.
 *
 * The room and the token travel in the environment, never the arguments, which other programs
 * on the computer can read. A guest's file came from someone else, so it's opened with Python
 * scripts inside the file switched off whatever the user's preference says; the host's own file
 * is opened the way they always open it.
 */
function launchCommand({ blender, filePath, launchScript, addonDir, serverUrl, token, username, roomId, role, trusted }) {
  const args = trusted ? [] : ['--disable-autoexec']
  args.push(filePath, '--python', launchScript)
  return {
    command: blender,
    args,
    env: {
      COLLAB_ADDON_DIR: addonDir,
      COLLAB_SERVER_URL: socketUrl(serverUrl),
      COLLAB_TOKEN: token,
      COLLAB_ROOM: roomId,
      COLLAB_USERNAME: username,
      COLLAB_ROLE: role,
    },
  }
}

module.exports = { findBlender, launchCommand, socketUrl }
