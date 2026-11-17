// Tests for the desktop app's own logic, without Electron: settings, finding Blender, moving
// the project file, and the whole launch against a fake server and a stand-in for Blender.
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { test, beforeEach, afterEach } = require('node:test')

const { findBlender, launchCommand } = require('../lib/blender.cjs')
const files = require('../lib/files.cjs')
const { launch, checked } = require('../lib/launch.cjs')
const { Settings } = require('../lib/settings.cjs')

const BLEND = Buffer.concat([Buffer.from('BLENDER-v502'), crypto.randomBytes(4096)])
const hashOf = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex')

let dir
let server
let serverUrl
let stored // what the fake server holds as the room's file
let requests

beforeEach(async () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'collab-desktop-'))
  stored = BLEND
  requests = []
  server = http.createServer((request, response) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => {
      requests.push({ method: request.method, url: request.url, auth: request.headers.authorization })
      if (request.headers.authorization !== 'Bearer t0k') {
        response.writeHead(401, { 'Content-Type': 'application/json' }).end('{"detail":"sign in first"}')
      } else if (request.method === 'PUT') {
        stored = Buffer.concat(chunks)
        response.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify({ hash: hashOf(stored) }))
      } else {
        response.writeHead(200).end(stored)
      }
    })
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  serverUrl = `http://127.0.0.1:${server.address().port}`
})

afterEach(() => {
  server.close()
  fs.rmSync(dir, { recursive: true, force: true })
})

test('settings survive a restart, and a host file is remembered per server and room', () => {
  const settings = new Settings(dir)
  assert.equal(settings.values.serverUrl, 'http://localhost:8000')
  settings.setServerUrl(' http://10.0.0.5:8000/some/path ')
  settings.setHostFile('http://10.0.0.5:8000', 'studio', '/home/me/scene.blend')

  const reopened = new Settings(dir)
  assert.equal(reopened.values.serverUrl, 'http://10.0.0.5:8000')
  assert.equal(reopened.hostFile('http://10.0.0.5:8000/', 'studio'), '/home/me/scene.blend')
  assert.equal(reopened.hostFile('http://elsewhere:8000', 'studio'), null)

  reopened.setHostFile('http://10.0.0.5:8000', 'studio', null)
  assert.equal(new Settings(dir).hostFile('http://10.0.0.5:8000', 'studio'), null)
})

test('a server address must be http or https', () => {
  const settings = new Settings(dir)
  assert.throws(() => settings.setServerUrl('file:///etc/passwd'), /http/)
  assert.throws(() => settings.setServerUrl('not a url'))
})

test('Blender is found in the usual place for each system', () => {
  const mac = '/Applications/Blender.app/Contents/MacOS/Blender'
  assert.equal(findBlender({ platform: 'darwin', env: {}, exists: (p) => p === mac }), mac)
  assert.equal(findBlender({ platform: 'linux', env: { PATH: '/usr/local/bin:/usr/bin' }, exists: (p) => p === '/usr/bin/blender' }), '/usr/bin/blender')
  assert.equal(findBlender({ platform: 'darwin', env: {}, exists: () => false }), null)
})

test('a chosen Blender wins, and a macOS app bundle resolves to the program inside it', () => {
  const inside = '/Users/me/Apps/Blender.app/Contents/MacOS/Blender'
  assert.equal(findBlender({ chosen: '/Users/me/Apps/Blender.app', exists: (p) => p === inside }), inside)
  assert.equal(findBlender({ chosen: '/opt/blender/blender', exists: () => true }), '/opt/blender/blender')
  assert.equal(findBlender({ chosen: '/gone/blender', exists: () => false }), null)
})

test('the launch command keeps the token out of the arguments', () => {
  const base = { blender: '/b', filePath: '/f.blend', launchScript: '/l.py', addonDir: '/addon', serverUrl: 'https://collab.example', token: 't0k', username: 'lucas', roomId: 'studio' }
  const host = launchCommand({ ...base, role: 'owner', trusted: true })
  const guest = launchCommand({ ...base, role: 'editor', trusted: false })

  assert.deepEqual(host.args, ['/f.blend', '--python', '/l.py'])
  assert.deepEqual(guest.args, ['--disable-autoexec', '/f.blend', '--python', '/l.py'])
  assert.ok(!JSON.stringify(host.args).includes('t0k'))
  assert.deepEqual(host.env, {
    COLLAB_ADDON_DIR: '/addon',
    COLLAB_SERVER_URL: 'wss://collab.example',
    COLLAB_TOKEN: 't0k',
    COLLAB_ROOM: 'studio',
    COLLAB_USERNAME: 'lucas',
    COLLAB_ROLE: 'owner',
  })
})

test('upload sends the file with its name, and a refusal carries the server\'s reason', async () => {
  const filePath = path.join(dir, 'my scene.blend')
  fs.writeFileSync(filePath, BLEND)

  const result = await files.upload({ serverUrl, token: 't0k', roomId: 'studio', filePath })

  assert.equal(result.hash, hashOf(BLEND))
  assert.equal(requests[0].url, '/api/rooms/studio/file?name=my%20scene.blend')
  await assert.rejects(files.upload({ serverUrl, token: 'bad', roomId: 'studio', filePath }), /Sign in first/)
})

test('download checks the content and leaves nothing behind when it is wrong', async () => {
  const target = path.join(dir, 'cache', 'scene.blend')

  await files.download({ serverUrl, token: 't0k', roomId: 'studio', target, expectedHash: hashOf(BLEND) })
  assert.deepEqual(fs.readFileSync(target), BLEND)

  const other = path.join(dir, 'cache', 'other.blend')
  await assert.rejects(
    files.download({ serverUrl, token: 't0k', roomId: 'studio', target: other, expectedHash: 'f'.repeat(64) }),
    /doesn't match/,
  )
  assert.deepEqual(fs.readdirSync(path.dirname(other)), ['scene.blend'])
})

test('a file name from the server can never leave the cache folder', () => {
  assert.equal(files.safeName('scene.blend'), 'scene.blend')
  assert.equal(files.safeName('../../.ssh/authorized_keys'), 'project.blend')
  assert.equal(files.safeName('..\\..\\evil.blend'), 'evil.blend')
  assert.equal(files.safeName('.blend'), 'project.blend')
  assert.equal(files.safeName('a/b/c d.blend'), 'c d.blend')
})

test('what the page asks to launch is checked first', () => {
  const good = { serverUrl, token: 't0k', username: 'lucas', roomId: 'studio', role: 'editor', fileHash: 'a'.repeat(64), fileName: 'scene.blend' }
  assert.equal(checked(good).roomId, 'studio')
  assert.throws(() => checked({ ...good, roomId: '../etc' }), /room name/)
  assert.throws(() => checked({ ...good, role: 'admin' }), /role/)
  assert.throws(() => checked({ ...good, fileHash: 'nope' }), /no project file/)
  assert.throws(() => checked({ ...good, token: '' }), /Log in/)
  assert.throws(() => checked({ ...good, serverUrl: 'file:///x' }), /http/)
})

// A stand-in for Blender: a script that records its arguments and the room it was given.
function fakeBlender() {
  const record = path.join(dir, 'launched.json')
  const blender = path.join(dir, 'blender')
  fs.writeFileSync(
    blender,
    `#!/usr/bin/env node\nrequire('fs').writeFileSync(${JSON.stringify(record)}, JSON.stringify({ args: process.argv.slice(2), room: process.env.COLLAB_ROOM, role: process.env.COLLAB_ROLE, token: process.env.COLLAB_TOKEN, url: process.env.COLLAB_SERVER_URL }))\n`,
    { mode: 0o755 },
  )
  const launched = async () => {
    for (let attempt = 0; attempt < 100 && !fs.existsSync(record); attempt++) await new Promise((r) => setTimeout(r, 20))
    return JSON.parse(fs.readFileSync(record, 'utf8'))
  }
  return { blender, launched }
}

function launchWith(overrides = {}) {
  const { blender, launched } = fakeBlender()
  const settings = new Settings(dir)
  settings.setBlenderPath(blender)
  const steps = []
  const request = { serverUrl, token: 't0k', username: 'lucas', roomId: 'studio', role: 'editor', fileHash: hashOf(BLEND), fileName: 'scene.blend', ...overrides }
  const options = { settings, cacheDir: path.join(dir, 'rooms'), launchScript: '/app/launch.py', addonDir: '/app/addon', progress: (step) => steps.push(step) }
  return { settings, steps, launched, run: () => launch(request, options) }
}

test('a guest gets the room\'s file downloaded and opened with scripts off', async () => {
  const { run, launched, steps } = launchWith()

  await run()

  const blender = await launched()
  const opened = blender.args[1]
  assert.deepEqual([blender.args[0], blender.args[2], blender.args[3]], ['--disable-autoexec', '--python', '/app/launch.py'])
  assert.ok(opened.startsWith(path.join(dir, 'rooms')) && opened.endsWith(path.join('studio', 'scene.blend')))
  assert.deepEqual(fs.readFileSync(opened), BLEND)
  assert.deepEqual([blender.room, blender.role, blender.token, blender.url], ['studio', 'editor', 't0k', serverUrl.replace('http', 'ws')])
  assert.deepEqual(steps, ['Downloading the project file…', 'Opening Blender…'])
})

test('a guest\'s copy is reused while it matches, and fetched again once it doesn\'t', async () => {
  const first = launchWith()
  await first.run()
  const opened = (await first.launched()).args[1]
  assert.equal(requests.length, 1)

  await launchWith().run() // same content: no second download
  assert.equal(requests.length, 1)

  fs.appendFileSync(opened, 'the guest saved their own changes over the copy')
  await launchWith().run()
  assert.equal(requests.length, 2)
  assert.deepEqual(fs.readFileSync(opened), BLEND)
})

test('the host opens their own file, uploading it first if it changed', async () => {
  const own = path.join(dir, 'My Project.blend')
  fs.writeFileSync(own, BLEND)
  const unchanged = launchWith({ role: 'owner' })
  unchanged.settings.setHostFile(serverUrl, 'studio', own)

  await unchanged.run()
  assert.deepEqual((await unchanged.launched()).args, [own, '--python', '/app/launch.py']) // scripts as the host has them
  assert.equal(requests.length, 0)

  const edited = Buffer.concat([BLEND, Buffer.from('edited outside the room')])
  fs.writeFileSync(own, edited)
  const changed = launchWith({ role: 'owner' })
  await changed.run()
  assert.deepEqual(stored, edited)
  assert.deepEqual(changed.steps, ['Sharing your latest file with the room…', 'Opening Blender…'])
})

test('a host on a computer without the file gets a downloaded copy', async () => {
  const { run, launched } = launchWith({ role: 'owner' })
  await run()
  assert.ok((await launched()).args.includes('--disable-autoexec'))
})

test('a missing Blender, or one that won\'t start, is explained', async () => {
  const missing = launchWith()
  missing.settings.setBlenderPath(path.join(dir, 'nowhere'))
  await assert.rejects(missing.run(), /Blender wasn't found/)

  const broken = launchWith()
  fs.chmodSync(path.join(dir, 'blender'), 0o644) // there, but not something that can run
  await assert.rejects(broken.run(), /couldn't be started/)
})
