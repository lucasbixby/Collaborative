// What changes inside the desktop app: the bridge picks files, uploads them, and launches Blender.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DesktopBridge } from '../platform'
import { ALICE, fakeServer, room } from './fakeServer'

const bridge = {
  getSettings: vi.fn(async () => ({ serverUrl: 'http://server.test:8000', blenderPath: '', detectedBlender: '/Applications/Blender.app' })),
  saveSettings: vi.fn(async (settings) => ({ ...settings, detectedBlender: '' })),
  pickBlendFile: vi.fn(async () => ({ id: 'file-1', name: 'scene.blend', size: 3 * 1024 * 1024 })),
  pickBlender: vi.fn(async () => null),
  hostFile: vi.fn(async () => {}),
  launch: vi.fn(async () => {}),
  forgetRoom: vi.fn(async () => {}),
  notify: vi.fn(),
  onProgress: vi.fn(() => () => {}),
} satisfies DesktopBridge

// The bridge is read when the modules load, so it's in place before they're imported.
async function renderDesktopApp() {
  window.collab = bridge
  vi.resetModules()
  const [{ default: App }, { AuthProvider }, { boot }] = await Promise.all([
    import('../App'),
    import('../AuthProvider'),
    import('../boot'),
  ])
  await boot()
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
}

const at = (path: string) => `http://server.test:8000${path}`
const me = { [`GET ${at('/api/auth/me')}`]: { status: 200, body: ALICE } }

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  window.localStorage.setItem('collab.token', 'tok-alice')
  return () => delete window.collab
})

describe('in the desktop app', () => {
  it("talks to the server set in settings and stays logged in between launches", async () => {
    const server = fakeServer({ ...me, [`GET ${at('/api/rooms')}`]: { status: 200, body: [room()] } })
    await renderDesktopApp()

    expect(await screen.findByRole('button', { name: /studio/ })).toBeTruthy()
    expect(server.calls.every((call) => call.path.startsWith('http://server.test:8000/'))).toBe(true)
    expect(server.calls[0].authorization).toBe('Bearer tok-alice')
  })

  it('launches Blender into the room with everything the app needs', async () => {
    fakeServer({
      ...me,
      [`GET ${at('/api/rooms')}`]: { status: 200, body: [room()] },
      [`GET ${at('/api/rooms/studio')}`]: { status: 200, body: { ...room(), members: [] } },
    })
    await renderDesktopApp()
    fireEvent.click(await screen.findByRole('button', { name: /studio/ }))

    fireEvent.click(await screen.findByRole('button', { name: 'Launch Blender' }))

    expect(await screen.findByText('Blender is opening in this room.')).toBeTruthy()
    expect(bridge.launch).toHaveBeenCalledWith({
      serverUrl: 'http://server.test:8000',
      token: 'tok-alice',
      username: 'alice',
      roomId: 'studio',
      role: 'owner',
      fileHash: 'abc123',
      fileName: 'scene.blend',
    })
  })

  it("shows why Blender couldn't be launched", async () => {
    bridge.launch.mockRejectedValueOnce(new Error("Blender wasn't found. Choose it in Settings."))
    fakeServer({
      ...me,
      [`GET ${at('/api/rooms')}`]: { status: 200, body: [room()] },
      [`GET ${at('/api/rooms/studio')}`]: { status: 200, body: { ...room(), members: [] } },
    })
    await renderDesktopApp()
    fireEvent.click(await screen.findByRole('button', { name: /studio/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Launch Blender' }))

    expect((await screen.findByRole('alert')).textContent).toBe("Blender wasn't found. Choose it in Settings.")
    expect((screen.getByRole('button', { name: 'Launch Blender' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('hosts a room from a file picked natively, which the app uploads and remembers', async () => {
    const server = fakeServer({
      ...me,
      [`GET ${at('/api/rooms')}`]: { status: 200, body: [] },
      [`POST ${at('/api/rooms')}`]: { status: 201, body: room({ file: null }) },
    })
    await renderDesktopApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Host room' }))

    fireEvent.click(screen.getByRole('button', { name: 'Choose .blend file' }))
    expect(await screen.findByText('3.0 MB')).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/room name/i), { target: { value: 'studio' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'open sesame' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create room' }))

    await waitFor(() =>
      expect(bridge.hostFile).toHaveBeenCalledWith({
        serverUrl: 'http://server.test:8000',
        token: 'tok-alice',
        roomId: 'studio',
        fileId: 'file-1',
      }),
    )
    expect(server.calls.some((call) => call.method === 'PUT')).toBe(false) // the app uploads, not the page
  })

  it('raises a system notification once for each save request', async () => {
    const asking = room({ save_requests: [{ id: 'req1', username: 'bob', requested_at: '' }] })
    fakeServer({ ...me, [`GET ${at('/api/rooms')}`]: { status: 200, body: [asking] } })
    await renderDesktopApp()

    await screen.findByRole('dialog', { name: 'bob would like to save the project' })
    document.dispatchEvent(new Event('visibilitychange')) // another refresh with the same request
    await waitFor(() => expect(bridge.notify).toHaveBeenCalledTimes(1))
    expect(bridge.notify).toHaveBeenCalledWith('Collaborative', 'bob would like to save studio')
  })

  it('saves the server address from Settings', async () => {
    fakeServer({ ...me, [`GET ${at('/api/rooms')}`]: { status: 200, body: [] } })
    await renderDesktopApp()
    fireEvent.click(await screen.findByRole('button', { name: 'Settings' }))

    const settings = within(await screen.findByRole('dialog', { name: 'Settings' }))
    await waitFor(() => expect((settings.getByLabelText('Server address') as HTMLInputElement).value).toBe('http://server.test:8000'))
    fireEvent.change(settings.getByLabelText('Server address'), { target: { value: ' http://10.0.0.5:8000 ' } })
    fireEvent.click(settings.getByRole('button', { name: 'Save settings' }))

    await waitFor(() => expect(bridge.saveSettings).toHaveBeenCalledWith({ serverUrl: 'http://10.0.0.5:8000' }))
  })
})
