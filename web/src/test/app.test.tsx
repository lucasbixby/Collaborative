// The UI's main flows against a fake server (#22).
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AuthProvider } from '../AuthProvider'
import { ALICE, fakeServer, signedIn } from './fakeServer'

function renderApp(path = '/') {
  window.history.replaceState(null, '', path)
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
}

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const STUDIO = {
  room_id: 'studio',
  role: 'owner',
  created_at: '2026-11-09T12:00:00Z',
  members: [
    { username: 'alice', role: 'owner', joined_at: '2026-11-09T12:00:00Z' },
    { username: 'bob', role: 'editor', joined_at: '2026-11-09T12:05:00Z' },
  ],
}

const roomRoutes = (users: unknown[] = []) => ({
  'GET /api/auth/me': { status: 200, body: ALICE },
  'GET /api/rooms/studio': { status: 200, body: STUDIO },
  'GET /api/rooms/studio/presence': { status: 200, body: { room_id: 'studio', users } },
})

describe('sign in', () => {
  it('signs in and shows my rooms, sending the token from then on', async () => {
    const server = fakeServer({
      'POST /api/auth/login': { status: 200, body: { token: 'tok-alice', user: ALICE } },
      'GET /api/rooms': { status: 200, body: [{ room_id: 'studio', role: 'owner', created_at: '' }] },
    })
    renderApp()

    fill(/username/i, 'alice')
    fill(/password/i, 'correct horse')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('link', { name: 'studio' })).toBeTruthy()
    expect(screen.getByText('alice')).toBeTruthy() // in the header
    expect(server.calls[0].body).toEqual({ username: 'alice', password: 'correct horse' })
    expect(server.calls[1].authorization).toBe('Bearer tok-alice')
    expect(window.sessionStorage.getItem('collab.token')).toBe('tok-alice')
  })

  it("shows the server's message when sign-in fails, and stays signed out", async () => {
    fakeServer({
      'POST /api/auth/login': { status: 401, body: { detail: 'wrong username or password' } },
    })
    renderApp()

    fill(/username/i, 'alice')
    fill(/password/i, 'nope')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect((await screen.findByRole('alert')).textContent).toBe('wrong username or password')
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
  })

  it('registers, then signs in, and shows validation messages field by field', async () => {
    fakeServer({
      'POST /api/auth/register': ({ body }) =>
        (body as { password: string }).password.length < 8
          ? {
              status: 422,
              body: { detail: [{ loc: ['body', 'password'], msg: 'String should have at least 8 characters' }] },
            }
          : { status: 201, body: ALICE },
      'POST /api/auth/login': { status: 200, body: { token: 'tok-alice', user: ALICE } },
      'GET /api/rooms': { status: 200, body: [] },
    })
    renderApp()
    fireEvent.click(screen.getByRole('button', { name: 'Create an account' }))

    fill(/username/i, 'alice')
    fill(/password/i, 'short')
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect((await screen.findByRole('alert')).textContent).toBe(
      'password: String should have at least 8 characters',
    )

    fill(/password/i, 'long enough')
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText(/No rooms yet/)).toBeTruthy()
  })
})

describe('signing out', () => {
  it('any 401 signs out and shows the sign-in page, not a crash', async () => {
    signedIn('expired')
    fakeServer({
      'GET /api/auth/me': { status: 401, body: { detail: 'invalid or expired token; sign in again' } },
    })
    renderApp('/rooms/studio')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
    expect(window.location.pathname).toBe('/rooms/studio') // signing in lands back here
  })

  it('a 401 later on, mid-page, signs out too', async () => {
    signedIn()
    fakeServer({
      'GET /api/auth/me': { status: 200, body: ALICE },
      'GET /api/rooms': { status: 401, body: { detail: 'invalid or expired token; sign in again' } },
    })
    renderApp()

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
  })

  it('Sign out forgets the token', async () => {
    signedIn()
    fakeServer({
      'GET /api/auth/me': { status: 200, body: ALICE },
      'GET /api/rooms': { status: 200, body: [] },
    })
    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(window.sessionStorage.getItem('collab.token')).toBeNull()
  })
})

describe('rooms', () => {
  it('a taken room id says so', async () => {
    signedIn()
    fakeServer({
      'GET /api/auth/me': { status: 200, body: ALICE },
      'GET /api/rooms': { status: 200, body: [] },
      'POST /api/rooms': { status: 409, body: { detail: "room 'demo' exists" } },
    })
    renderApp()

    await screen.findByLabelText(/room id/i)
    fill(/room id/i, 'demo')
    fireEvent.click(await screen.findByRole('button', { name: 'Create room' }))

    expect((await screen.findByRole('alert')).textContent).toBe('"demo" is taken. Pick another name.')
  })

  it('checks the room-id rule as you type', async () => {
    signedIn()
    fakeServer({
      'GET /api/auth/me': { status: 200, body: ALICE },
      'GET /api/rooms': { status: 200, body: [] },
    })
    renderApp()

    await screen.findByLabelText(/room id/i)
    fill(/room id/i, 'has space')

    const button = (await screen.findByRole('button', { name: 'Create room' })) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(screen.getByLabelText(/room id/i).getAttribute('aria-invalid')).toBe('true')
  })

  it('creating a room goes to it', async () => {
    signedIn()
    fakeServer({
      ...roomRoutes(),
      'GET /api/rooms': { status: 200, body: [] },
      'POST /api/rooms': { status: 201, body: { room_id: 'studio', role: 'owner', created_at: '' } },
    })
    renderApp()

    await screen.findByLabelText(/room id/i)
    fill(/room id/i, 'studio')
    fireEvent.click(await screen.findByRole('button', { name: 'Create room' }))

    expect(await screen.findByRole('heading', { name: /studio/ })).toBeTruthy()
    expect(window.location.pathname).toBe('/rooms/studio')
  })
})

describe('room page', () => {
  it('creates an invite and copies its link, then revokes it', async () => {
    signedIn()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const server = fakeServer({
      ...roomRoutes(),
      'POST /api/rooms/studio/invites': {
        status: 201,
        body: { code: 'abc123', room_id: 'studio', role: 'viewer', expires_at: '2026-11-10T12:00:00Z' },
      },
      'DELETE /api/rooms/studio/invites/abc123': { status: 204 },
    })
    renderApp('/rooms/studio')

    fireEvent.change(await screen.findByLabelText('Role'), { target: { value: 'viewer' } })
    fill(/expires in/i, '48')
    fireEvent.click(screen.getByRole('button', { name: 'Create invite link' }))

    const link = `${window.location.origin}/join/abc123`
    expect(await screen.findByText(link)).toBeTruthy()
    expect(server.calls.find((call) => call.method === 'POST')?.body).toEqual({
      role: 'viewer',
      expires_in_hours: 48,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Copy link' }))
    expect(writeText).toHaveBeenCalledWith(link)
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    expect(await screen.findByText(/revoked/)).toBeTruthy()
  })

  it('shows who is connected, and polls while visible', async () => {
    signedIn()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let users = [{ username: 'bob', role: 'editor', connections: 2 }]
    const server = fakeServer({
      ...roomRoutes(),
      'GET /api/rooms/studio/presence': () => ({ status: 200, body: { room_id: 'studio', users } }),
    })
    renderApp('/rooms/studio')

    const presence = await screen.findByRole('region', { name: 'Connected now' })
    await within(presence).findByText('bob')
    expect(within(presence).getByText(/2 connections/)).toBeTruthy()

    users = []
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
    expect(await within(presence).findByText(/Nobody is connected/)).toBeTruthy()
    expect(server.calls.filter((call) => call.path.endsWith('/presence')).length).toBeGreaterThan(1)
    vi.useRealTimers()
  })

  it('shows the Blender details with copy buttons', async () => {
    signedIn()
    fakeServer(roomRoutes())
    renderApp('/rooms/studio')

    expect(await screen.findByRole('button', { name: 'Copy room ID' })).toBeTruthy()
    expect(screen.getByText(`ws://${window.location.host}`)).toBeTruthy()
    expect(screen.getByText(/sign in to the add-on with this same account/)).toBeTruthy()
  })

  it("shows the server's error when the last owner can't be removed", async () => {
    signedIn()
    fakeServer({
      ...roomRoutes(),
      'DELETE /api/rooms/studio/members/alice': {
        status: 409,
        body: { detail: 'a room needs an owner: make someone else owner first' },
      },
    })
    renderApp('/rooms/studio')

    const removes = await screen.findAllByRole('button', { name: 'Remove' })
    fireEvent.click(removes[0])
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove' }))

    expect((await screen.findByRole('alert')).textContent).toBe(
      'a room needs an owner: make someone else owner first',
    )
  })

  it('an owner changes a role', async () => {
    signedIn()
    const server = fakeServer({
      ...roomRoutes(),
      'PATCH /api/rooms/studio/members/bob': { status: 200, body: { username: 'bob', role: 'viewer', joined_at: '' } },
    })
    renderApp('/rooms/studio')

    fireEvent.change(await screen.findByLabelText('Role for bob'), { target: { value: 'viewer' } })

    await waitFor(() => expect(server.calls.some((call) => call.method === 'PATCH')).toBe(true))
    expect(server.calls.find((call) => call.method === 'PATCH')?.body).toEqual({ role: 'viewer' })
  })
})

describe('join by link', () => {
  it('signed out: sign in first, then join and land on the room', async () => {
    const server = fakeServer({
      ...roomRoutes(),
      'POST /api/auth/login': { status: 200, body: { token: 'tok-alice', user: ALICE } },
      'POST /api/rooms/join/abc123': { status: 200, body: { room_id: 'studio', role: 'editor' } },
    })
    renderApp('/join/abc123')

    expect(screen.getByText(/You've been invited to a room/)).toBeTruthy()
    fill(/username/i, 'alice')
    fill(/password/i, 'correct horse')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: /studio/ })).toBeTruthy()
    expect(window.location.pathname).toBe('/rooms/studio')
    const joins = server.calls.filter((call) => call.path === '/api/rooms/join/abc123')
    expect(joins).toHaveLength(1)
    expect(joins[0].authorization).toBe('Bearer tok-alice')
  })

  it('an expired link says so', async () => {
    signedIn()
    fakeServer({
      'GET /api/auth/me': { status: 200, body: ALICE },
      'POST /api/rooms/join/old': { status: 410, body: { detail: 'this invite has expired' } },
    })
    renderApp('/join/old')

    expect((await screen.findByRole('alert')).textContent).toBe('this invite has expired')
  })
})

describe('server down', () => {
  it('says the server is unreachable instead of a blank page', async () => {
    signedIn()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderApp()

    expect((await screen.findByRole('alert')).textContent).toMatch(/Can't reach the server/)
  })
})
