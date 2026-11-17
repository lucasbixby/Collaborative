// The UI's main flows in a browser, against a fake server. The desktop app's extras (launching
// Blender, the native file picker) are covered in desktop.test.tsx.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from '../App'
import { AuthProvider } from '../AuthProvider'
import { ALICE, fakeServer, room, signedIn } from './fakeServer'

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
}

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const click = (name: string | RegExp) => fireEvent.click(screen.getByRole('button', { name }))
const me = { 'GET /api/auth/me': { status: 200, body: ALICE } }
const members = (...names: [string, string][]) => names.map(([username, role]) => ({ username, role, joined_at: '' }))

describe('logging in', () => {
  it('logs in and shows my rooms, sending the token from then on', async () => {
    const server = fakeServer({
      'POST /api/auth/login': { status: 200, body: { token: 'tok-alice', user: ALICE } },
      'GET /api/rooms': { status: 200, body: [room()] },
    })
    renderApp()

    fill(/username/i, 'alice')
    fill(/password/i, 'correct horse')
    click('Log in')

    expect(await screen.findByRole('button', { name: /studio/ })).toBeTruthy()
    expect(screen.getByText('( alice )')).toBeTruthy()
    expect(server.calls[0].body).toEqual({ username: 'alice', password: 'correct horse' })
    expect(server.calls[1].authorization).toBe('Bearer tok-alice')
    expect(window.sessionStorage.getItem('collab.token')).toBe('tok-alice')
  })

  it("shows the server's message when it fails, and stays logged out", async () => {
    fakeServer({ 'POST /api/auth/login': { status: 401, body: { detail: 'wrong username or password' } } })
    renderApp()

    fill(/username/i, 'alice')
    fill(/password/i, 'nope')
    click('Log in')

    expect((await screen.findByRole('alert')).textContent).toBe('Wrong username or password')
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
  })

  it('creates an account, then logs in with it', async () => {
    const server = fakeServer({
      'POST /api/auth/register': { status: 201, body: ALICE },
      'POST /api/auth/login': { status: 200, body: { token: 'tok-alice', user: ALICE } },
      'GET /api/rooms': { status: 200, body: [] },
    })
    renderApp()

    click('Create an account')
    fill(/username/i, 'alice')
    fill(/password/i, 'correct horse')
    click('Create account')

    expect(await screen.findByText(/No rooms yet/)).toBeTruthy()
    expect(server.calls.map((call) => call.path)).toEqual(['/api/auth/register', '/api/auth/login', '/api/rooms'])
  })

  it('shows a validation error from registering as "field: message"', async () => {
    fakeServer({
      'POST /api/auth/register': {
        status: 422,
        body: { detail: [{ loc: ['body', 'password'], msg: 'String should have at least 8 characters' }] },
      },
    })
    renderApp()

    click('Create an account')
    fill(/username/i, 'alice')
    fill(/password/i, 'short')
    click('Create account')

    expect((await screen.findByRole('alert')).textContent).toBe('password: String should have at least 8 characters')
  })

  it('logs out when a stored token is rejected, and on Log out', async () => {
    signedIn('stale')
    fakeServer({ 'GET /api/auth/me': { status: 401, body: { detail: 'invalid or expired token' } } })
    const first = renderApp()
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeTruthy()
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
    first.unmount()

    signedIn()
    fakeServer({ ...me, 'GET /api/rooms': { status: 200, body: [] } })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeTruthy()
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
  })

  it('says so when the server is down, with a way to try again', async () => {
    signedIn()
    globalThis.fetch = (() => Promise.reject(new TypeError('Failed to fetch'))) as typeof fetch
    renderApp()

    expect((await screen.findByRole('alert')).textContent).toMatch(/Can't reach the server/)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })
})

describe('the dashboard', () => {
  it('separates rooms I host from rooms I joined, with who is in each', async () => {
    signedIn()
    fakeServer({
      ...me,
      'GET /api/rooms': {
        status: 200,
        body: [
          room({ online: [{ username: 'bob', role: 'editor', connections: 1 }, { username: 'carol', role: 'editor', connections: 1 }] }),
          room({ room_id: 'garage', role: 'editor', host: 'bob' }),
        ],
      },
    })
    renderApp()

    const hosting = within(await screen.findByRole('region', { name: 'Hosting' }))
    const joined = within(screen.getByRole('region', { name: 'Joined' }))
    expect(hosting.getByText('bob and carol are in the room')).toBeTruthy()
    expect(hosting.getByText('You host this room')).toBeTruthy()
    expect(joined.getByText('Hosted by bob')).toBeTruthy()
    expect(joined.getByText('Empty')).toBeTruthy()
  })

  it('keeps the list fresh while the window is visible', async () => {
    signedIn()
    const online: unknown[] = []
    const server = fakeServer({ ...me, 'GET /api/rooms': () => ({ status: 200, body: [room({ online: [...online] })] }) })
    renderApp()
    expect(await screen.findByText('Empty')).toBeTruthy()

    online.push({ username: 'bob', role: 'editor', connections: 1 })
    document.dispatchEvent(new Event('visibilitychange'))

    expect(await screen.findByText('bob is in the room')).toBeTruthy()
    expect(server.calls.filter((call) => call.path === '/api/rooms').length).toBe(2)
  })
})

describe('hosting a room', () => {
  it('creates the room, uploads the chosen file, and opens the room', async () => {
    signedIn()
    const rooms: unknown[] = []
    const server = fakeServer({
      ...me,
      'GET /api/rooms': () => ({ status: 200, body: rooms }),
      'POST /api/rooms': () => {
        rooms.push(room())
        return { status: 201, body: room({ file: null }) }
      },
      'PUT /api/rooms/studio/file?name=scene.blend': { status: 200, body: room().file },
      'GET /api/rooms/studio': { status: 200, body: { ...room(), members: members(['alice', 'owner']) } },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Host room' }))

    const file = new File(['BLENDER-v502'], 'scene.blend')
    fireEvent.change(screen.getByLabelText('Blender file'), { target: { files: [file] } })
    fill(/room name/i, 'studio')
    fill(/password/i, 'open sesame')
    click('Create room')

    expect(await screen.findByRole('dialog', { name: 'studio' })).toBeTruthy()
    const created = server.calls.find((call) => call.method === 'POST' && call.path === '/api/rooms')
    expect(created?.body).toEqual({ room_id: 'studio', password: 'open sesame' })
    expect(server.calls.find((call) => call.method === 'PUT')?.body).toBe(file)
  })

  it('needs a file and a valid name before it can be created', async () => {
    signedIn()
    fakeServer({ ...me, 'GET /api/rooms': { status: 200, body: [] } })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Host room' }))

    const create = screen.getByRole('button', { name: 'Create room' }) as HTMLButtonElement
    expect(create.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Blender file'), { target: { files: [new File(['x'], 'a.blend')] } })
    fill(/room name/i, 'has a space')
    expect(create.disabled).toBe(true)
    fill(/room name/i, 'studio')
    expect(create.disabled).toBe(false)
  })

  it('says a taken name is taken', async () => {
    signedIn()
    fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [] },
      'POST /api/rooms': { status: 409, body: { detail: "room 'studio' exists" } },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Host room' }))
    fireEvent.change(screen.getByLabelText('Blender file'), { target: { files: [new File(['x'], 'a.blend')] } })
    fill(/room name/i, 'studio')
    fill(/password/i, 'open sesame')
    click('Create room')

    expect((await screen.findByRole('alert')).textContent).toBe('"studio" is taken. Pick another name.')
  })

  it("takes the room back if its file can't be uploaded", async () => {
    signedIn()
    const server = fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [] },
      'POST /api/rooms': { status: 201, body: room({ file: null }) },
      'PUT /api/rooms/studio/file?name=a.txt': { status: 422, body: { detail: 'not a .blend file' } },
      'DELETE /api/rooms/studio': { status: 204 },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Host room' }))
    fireEvent.change(screen.getByLabelText('Blender file'), { target: { files: [new File(['x'], 'a.txt')] } })
    fill(/room name/i, 'studio')
    fill(/password/i, 'open sesame')
    click('Create room')

    expect((await screen.findByRole('alert')).textContent).toBe('Not a .blend file')
    expect(server.calls.some((call) => call.method === 'DELETE' && call.path === '/api/rooms/studio')).toBe(true)
  })
})

describe('joining a room', () => {
  it('joins with the name and password and opens the room', async () => {
    signedIn()
    const rooms: unknown[] = []
    const theirs = room({ role: 'editor', host: 'bob' })
    const server = fakeServer({
      ...me,
      'GET /api/rooms': () => ({ status: 200, body: rooms }),
      'POST /api/rooms/join': () => {
        rooms.push(theirs)
        return { status: 200, body: theirs }
      },
      'GET /api/rooms/studio': { status: 200, body: { ...theirs, members: members(['bob', 'owner'], ['alice', 'editor']) } },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Join room' }))

    fill(/room name/i, ' studio ')
    fill(/password/i, 'open sesame')
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Join room' }))

    const opened = within(await screen.findByRole('dialog', { name: 'studio' }))
    expect(opened.getByText('( Hosted by bob )')).toBeTruthy()
    expect(server.calls.find((call) => call.path === '/api/rooms/join')?.body).toEqual({
      room_id: 'studio',
      password: 'open sesame',
    })
  })

  it("shows the server's refusal", async () => {
    signedIn()
    fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [] },
      'POST /api/rooms/join': { status: 403, body: { detail: 'wrong room name or password' } },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Join room' }))
    fill(/room name/i, 'studio')
    fill(/password/i, 'nope')
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Join room' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Wrong room name or password')
  })
})

describe('a room', () => {
  const detail = { ...room(), members: members(['alice', 'owner'], ['bob', 'editor']) }
  const routes = {
    ...me,
    'GET /api/rooms': { status: 200, body: [room()] },
    'GET /api/rooms/studio': { status: 200, body: detail },
  }

  async function open() {
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: /studio/ }))
    return within(await screen.findByRole('dialog', { name: 'studio' }))
  }

  it('in a browser, points to the desktop app for launching Blender', async () => {
    signedIn()
    fakeServer(routes)
    const dialog = await open()

    expect(dialog.getByText(/desktop app to launch Blender/)).toBeTruthy()
    expect(dialog.queryByRole('button', { name: 'Launch Blender' })).toBeNull()
  })

  it('lets the host change what someone can do, and remove them after confirming', async () => {
    signedIn()
    const server = fakeServer({
      ...routes,
      'PATCH /api/rooms/studio/members/bob': { status: 200, body: { username: 'bob', role: 'viewer', joined_at: '' } },
      'DELETE /api/rooms/studio/members/bob': { status: 204 },
    })
    const dialog = await open()

    fireEvent.change(await dialog.findByLabelText('Role for bob'), { target: { value: 'viewer' } })
    await waitFor(() => expect(server.calls.find((call) => call.method === 'PATCH')?.body).toEqual({ role: 'viewer' }))

    fireEvent.click(dialog.getByRole('button', { name: 'Remove' }))
    expect(server.calls.some((call) => call.method === 'DELETE')).toBe(false) // not until confirmed
    fireEvent.click(dialog.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(server.calls.some((call) => call.method === 'DELETE')).toBe(true))
  })

  it('lets the host delete the room after confirming', async () => {
    signedIn()
    const server = fakeServer({ ...routes, 'DELETE /api/rooms/studio': { status: 204 } })
    const dialog = await open()

    fireEvent.click(dialog.getByRole('button', { name: 'Delete room' }))
    fireEvent.click(dialog.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(server.calls.some((call) => call.method === 'DELETE' && call.path === '/api/rooms/studio')).toBe(true)
  })

  it('lets a guest leave, and shows no host controls', async () => {
    signedIn()
    const theirs = room({ role: 'editor', host: 'bob' })
    const server = fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [theirs] },
      'GET /api/rooms/studio': { status: 200, body: { ...theirs, members: members(['bob', 'owner'], ['alice', 'editor']) } },
      'DELETE /api/rooms/studio/members/alice': { status: 204 },
    })
    const dialog = await open()

    await dialog.findByText('bob')
    expect(dialog.queryByRole('combobox')).toBeNull()
    expect(dialog.queryByRole('button', { name: 'Delete room' })).toBeNull()
    fireEvent.click(dialog.getByRole('button', { name: 'Leave room' }))
    fireEvent.click(dialog.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(server.calls.some((call) => call.path === '/api/rooms/studio/members/alice')).toBe(true))
  })
})

describe('a save request', () => {
  const asking = room({ save_requests: [{ id: 'req1', username: 'bob', requested_at: '2026-11-16T12:30:00Z' }] })

  it('pops up for the host, and Approve tells the server', async () => {
    signedIn()
    const rooms = [asking]
    const server = fakeServer({
      ...me,
      'GET /api/rooms': () => ({ status: 200, body: rooms }),
      'POST /api/rooms/studio/save-requests/req1': () => {
        rooms[0] = room()
        return { status: 204 }
      },
    })
    renderApp()

    const popup = within(await screen.findByRole('dialog', { name: 'bob would like to save the project' }))
    fireEvent.click(popup.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(server.calls.find((call) => call.method === 'POST')?.body).toEqual({ approve: true })
  })

  it('Deny tells the server no', async () => {
    signedIn()
    const server = fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [asking] },
      'POST /api/rooms/studio/save-requests/req1': { status: 204 },
    })
    renderApp()

    fireEvent.click(await screen.findByRole('button', { name: 'Deny' }))

    await waitFor(() => expect(server.calls.find((call) => call.method === 'POST')?.body).toEqual({ approve: false }))
  })

  it("explains when approving can't save yet, and keeps the pop-up", async () => {
    signedIn()
    fakeServer({
      ...me,
      'GET /api/rooms': { status: 200, body: [asking] },
      'POST /api/rooms/studio/save-requests/req1': {
        status: 409,
        body: { detail: 'open this room in Blender first: the project is saved from your Blender' },
      },
    })
    renderApp()

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))

    expect((await screen.findByRole('alert')).textContent).toMatch(/Open this room in Blender first/)
    expect(screen.getByRole('dialog', { name: 'bob would like to save the project' })).toBeTruthy()
  })
})
