// My rooms, with my role in each, and a form to create one. The room-id rule is shown under
// the field and checked as you type; the server's 409 becomes "taken".
import { useEffect, useState, type FormEvent } from 'react'

import { api, ApiError, ROOM_ID_PATTERN, type Room } from '../api/client'
import { ErrorMessage } from '../components/ErrorMessage'
import { Link } from '../components/Link'
import { navigate } from '../navigation'

export function RoomsPage() {
  const [rooms, setRooms] = useState<Room[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [roomId, setRoomId] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    api.listRooms().then(setRooms, (caught: ApiError) => setError(caught.message))
  }, [])

  const invalid = roomId !== '' && !ROOM_ID_PATTERN.test(roomId)

  async function create(event: FormEvent) {
    event.preventDefault()
    setCreateError(null)
    try {
      const room = await api.createRoom(roomId)
      navigate(`/rooms/${encodeURIComponent(room.room_id)}`)
    } catch (caught) {
      const apiError = caught as ApiError
      setCreateError(
        apiError.status === 409 ? `"${roomId}" is taken. Pick another name.` : apiError.message,
      )
    }
  }

  return (
    <>
      <section className="card">
        <h1>My rooms</h1>
        <ErrorMessage error={error} />
        {rooms === null && !error && <p className="muted">Loading…</p>}
        {rooms?.length === 0 && (
          <p className="muted">No rooms yet. Create one below, or open an invite link.</p>
        )}
        {rooms && rooms.length > 0 && (
          <ul className="list">
            {rooms.map((room) => (
              <li key={room.room_id}>
                <Link to={`/rooms/${encodeURIComponent(room.room_id)}`}>{room.room_id}</Link>
                <span className={`badge ${room.role}`}>{room.role}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Create a room</h2>
        <form onSubmit={create}>
          <label>
            Room id
            <input
              name="room_id"
              required
              value={roomId}
              aria-invalid={invalid}
              aria-describedby="room-id-rule"
              onChange={(event) => setRoomId(event.target.value)}
            />
          </label>
          <p id="room-id-rule" className={invalid ? 'hint error' : 'hint'}>
            1–64 letters, digits, "_" or "-". It's what people type into the Blender panel.
          </p>
          <ErrorMessage error={createError} />
          <button type="submit" disabled={invalid || roomId === ''}>
            Create room
          </button>
        </form>
      </section>
    </>
  )
}
