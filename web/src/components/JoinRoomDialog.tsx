// Join a room someone else hosts, with its name and password.
import { useState, type FormEvent } from 'react'

import { api, ApiError, type Room } from '../api/client'
import { Dialog, ErrorMessage } from './Dialog'

export function JoinRoomDialog({ onClose, onDone }: { onClose: () => void; onDone: (room: Room) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      onDone(await api.joinRoom(name.trim(), password))
    } catch (caught) {
      setError((caught as ApiError).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title="Join a room" caption="Someone else's room" onClose={onClose}>
      <form onSubmit={submit}>
        <label>
          Room name
          <input name="room" autoFocus required value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          Password
          <input
            name="room-password"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <ErrorMessage error={error} />
        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'Joining…' : 'Join room'}
        </button>
      </form>
    </Dialog>
  )
}
