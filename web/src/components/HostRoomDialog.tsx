// Host a room: choose the .blend it starts from, name it, set its password. The desktop app
// picks the file natively and remembers where it is, since that's the file the host's saves
// update; a browser can only upload a copy.
import { useRef, useState, type FormEvent } from 'react'

import { api, ApiError, ROOM_NAME_PATTERN, serverUrl, type Room } from '../api/client'
import { useAuth } from '../auth'
import { desktop, type PickedFile } from '../platform'
import { Dialog, ErrorMessage } from './Dialog'

const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

export function HostRoomDialog({ onClose, onDone }: { onClose: () => void; onDone: (room: Room) => void }) {
  const { token } = useAuth()
  const [picked, setPicked] = useState<PickedFile | null>(null)
  const browserFile = useRef<File | null>(null)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<string | null>(null)
  const invalid = name !== '' && !ROOM_NAME_PATTERN.test(name)

  async function choose() {
    const file = await desktop!.pickBlendFile()
    if (file) setPicked(file)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    let created: Room | null = null
    try {
      setStep('Creating the room…')
      created = await api.hostRoom(name, password)
      setStep('Uploading the project file…')
      if (desktop) {
        await desktop.hostFile({ serverUrl: serverUrl(), token: token!, roomId: name, fileId: picked!.id })
      } else {
        await api.uploadFile(name, browserFile.current!)
      }
      onDone(created)
    } catch (caught) {
      // A room without its file is no use: take it back so the name is free to try again.
      if (created) await api.deleteRoom(name).catch(() => {})
      const message = caught instanceof ApiError || caught instanceof Error ? caught.message : String(caught)
      setError(caught instanceof ApiError && caught.status === 409 ? `"${name}" is taken. Pick another name.` : message)
      setStep(null)
    }
  }

  return (
    <Dialog title="Host a room" caption="New room" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="field">
          <span className="field-label">Blender file</span>
          {desktop ? (
            <div className="file-row">
              <button type="button" className="outline" onClick={choose}>
                {picked ? 'Choose another' : 'Choose .blend file'}
              </button>
              {picked && (
                <span className="file-name">
                  {picked.name} <span className="muted">{megabytes(picked.size)}</span>
                </span>
              )}
            </div>
          ) : (
            <input
              type="file"
              accept=".blend"
              aria-label="Blender file"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null
                browserFile.current = file
                setPicked(file ? { id: '', name: file.name, size: file.size } : null)
              }}
            />
          )}
          <p className="hint">The room starts from this file, and your saves go back to it.</p>
        </div>
        <label>
          Room name
          <input
            name="room"
            required
            value={name}
            aria-invalid={invalid}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <p className={invalid ? 'hint error' : 'hint'}>1–64 letters, digits, "_" or "-". People type it to join.</p>
        <label>
          Password
          <input
            name="room-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={4}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <p className="hint">Share it with the people you want in the room.</p>
        <ErrorMessage error={error} />
        <button type="submit" className="primary" disabled={!picked || invalid || step !== null}>
          {step ?? 'Create room'}
        </button>
      </form>
    </Dialog>
  )
}
