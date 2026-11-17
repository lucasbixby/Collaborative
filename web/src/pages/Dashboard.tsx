// The dashboard: the rooms I host and the ones I've joined, each with who is in it right now.
// The list is re-read every few seconds while the window is visible, which is also how a
// guest's save request reaches the host.
import { useCallback, useEffect, useRef, useState } from 'react'

import { api, ApiError, type Room } from '../api/client'
import { ErrorMessage } from '../components/Dialog'
import { DotField } from '../components/DotField'
import { HostRoomDialog } from '../components/HostRoomDialog'
import { JoinRoomDialog } from '../components/JoinRoomDialog'
import { RoomDialog } from '../components/RoomDialog'
import { SaveRequestDialog } from '../components/SaveRequestDialog'
import { desktop } from '../platform'

const REFRESH_MS = 3000
const names = new Intl.ListFormat('en', { style: 'long', type: 'conjunction' })

export function Dashboard() {
  const [rooms, setRooms] = useState<Room[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'host' | 'join' | null>(null)
  const [openRoom, setOpenRoom] = useState<string | null>(null)
  const announced = useRef(new Set<string>())

  const refresh = useCallback(async () => {
    try {
      setRooms(await api.listRooms())
      setError(null)
    } catch (caught) {
      setError((caught as ApiError).message)
    }
  }, [])

  useEffect(() => {
    const tick = () => document.visibilityState === 'visible' && refresh()
    queueMicrotask(refresh)
    const timer = window.setInterval(tick, REFRESH_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [refresh])

  const pending = (rooms ?? []).flatMap((room) =>
    room.save_requests.map((request) => ({ room, request })),
  )
  // A system notification once per request, for a host whose app is behind other windows.
  useEffect(() => {
    for (const { room, request } of pending) {
      if (announced.current.has(request.id)) continue
      announced.current.add(request.id)
      desktop?.notify('Collaborative', `${request.username} would like to save ${room.room_id}`)
    }
  }, [pending])

  const hosting = rooms?.filter((room) => room.role === 'owner') ?? []
  const joined = rooms?.filter((room) => room.role !== 'owner') ?? []
  const opened = rooms?.find((room) => room.room_id === openRoom)

  function created(room: Room) {
    setDialog(null)
    setOpenRoom(room.room_id)
    refresh()
  }

  return (
    <>
      <section className="actions-row">
        <h1>Rooms</h1>
        <div className="actions">
          <button type="button" className="primary" onClick={() => setDialog('host')}>
            Host room
          </button>
          <button type="button" className="outline" onClick={() => setDialog('join')}>
            Join room
          </button>
        </div>
      </section>
      <ErrorMessage error={error} />
      {rooms === null && !error && <p className="muted">Loading rooms…</p>}
      {rooms?.length === 0 && (
        <p className="empty">
          No rooms yet. Host one from a .blend file, or join a friend's with its name and password.
        </p>
      )}
      <RoomList title="Hosting" rooms={hosting} onOpen={setOpenRoom} />
      <RoomList title="Joined" rooms={joined} onOpen={setOpenRoom} />

      {dialog === 'host' && <HostRoomDialog onClose={() => setDialog(null)} onDone={created} />}
      {dialog === 'join' && <JoinRoomDialog onClose={() => setDialog(null)} onDone={created} />}
      {opened && (
        <RoomDialog
          key={opened.room_id}
          room={opened}
          onClose={() => setOpenRoom(null)}
          onChanged={refresh}
        />
      )}
      {pending[0] && (
        <SaveRequestDialog
          key={pending[0].request.id}
          room={pending[0].room}
          request={pending[0].request}
          onAnswered={refresh}
        />
      )}
    </>
  )
}

function RoomList({ title, rooms, onOpen }: { title: string; rooms: Room[]; onOpen: (id: string) => void }) {
  if (rooms.length === 0) return null
  return (
    <section className="room-section" aria-label={title}>
      <p className="caption">
        ( {title} ) <span className="count">{rooms.length}</span>
      </p>
      <ul className="rooms">
        {rooms.map((room) => (
          <li key={room.room_id}>
            <button type="button" className="room-card" onClick={() => onOpen(room.room_id)}>
              <DotField name={room.room_id} />
              <span className="room-name">{room.room_id}</span>
              <span className="room-meta">
                {room.role === 'owner' ? 'You host this room' : `Hosted by ${room.host}`}
              </span>
              <Presence room={room} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Presence({ room }: { room: Room }) {
  if (room.online.length === 0) {
    return (
      <span className="presence">
        <span className="pip empty" aria-hidden="true" /> Empty
      </span>
    )
  }
  return (
    <span className="presence">
      {room.online.map((user) => (
        <span key={user.username} className="pip" aria-hidden="true" />
      ))}
      <span>
        {names.format(room.online.map((user) => user.username))} {room.online.length === 1 ? 'is' : 'are'} in
        the room
      </span>
    </span>
  )
}
