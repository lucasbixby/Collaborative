// One room, opened from its card: who's in it, Launch Blender, and for the host the people in
// the room and deleting it.
import { useEffect, useState } from 'react'

import { api, ApiError, serverUrl, type Member, type Role, type Room } from '../api/client'
import { useAuth } from '../auth'
import { Presence } from '../pages/Dashboard'
import { desktop } from '../platform'
import { Dialog, ErrorMessage } from './Dialog'
import { DotField } from './DotField'

const message = (caught: unknown) => (caught instanceof Error ? caught.message : String(caught))

export function RoomDialog({ room, onClose, onChanged }: { room: Room; onClose: () => void; onChanged: () => void }) {
  const { user, token } = useAuth()
  const [members, setMembers] = useState<Member[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const host = room.role === 'owner'
  const online = room.online.length

  useEffect(() => {
    api.getRoom(room.room_id).then(
      (detail) => setMembers(detail.members),
      (caught) => setError(message(caught)),
    )
  }, [room.room_id, online])

  useEffect(() => desktop?.onProgress(setProgress), [])

  async function launch() {
    setError(null)
    setProgress('Getting ready…')
    try {
      await desktop!.launch({
        serverUrl: serverUrl(),
        token: token!,
        username: user!.username,
        roomId: room.room_id,
        role: room.role,
        fileHash: room.file!.hash,
        fileName: room.file!.name,
      })
      setProgress('Blender is opening in this room.')
      onChanged()
    } catch (caught) {
      setProgress(null)
      setError(message(caught))
    }
  }

  async function run(action: () => Promise<unknown>, close = false) {
    setError(null)
    setConfirming(null)
    try {
      await action()
      onChanged()
      if (close) onClose()
      else setMembers((await api.getRoom(room.room_id)).members)
    } catch (caught) {
      setError((caught as ApiError).message)
    }
  }

  const confirm = (key: string, label: string, action: () => Promise<unknown>, close = false) =>
    confirming === key ? (
      <button type="button" className="danger" onClick={() => run(action, close)}>
        Confirm
      </button>
    ) : (
      <button type="button" className="quiet" onClick={() => setConfirming(key)}>
        {label}
      </button>
    )

  return (
    <Dialog title={room.room_id} caption={host ? 'You host this room' : `Hosted by ${room.host}`} onClose={onClose} wide>
      <DotField name={room.room_id} columns={16} rows={4} />
      <Presence room={room} />
      <p className="file-line">
        {room.file ? (
          <>
            {room.file.name}
            <span className="muted"> last saved {new Date(room.file.updated_at).toLocaleString()}</span>
          </>
        ) : (
          <span className="muted">The host hasn't added the project file yet.</span>
        )}
      </p>

      {desktop ? (
        <button type="button" className="primary launch" disabled={!room.file || progress !== null} onClick={launch}>
          Launch Blender
        </button>
      ) : (
        <p className="hint">Open this room in the Collaborative desktop app to launch Blender.</p>
      )}
      {progress && (
        <p className="progress" role="status">
          {progress}
        </p>
      )}
      {room.role === 'viewer' && <p className="hint">You're viewing: you see every edit, and yours stay on your computer.</p>}
      <ErrorMessage error={error} />

      <section className="people">
        <p className="caption">( People )</p>
        <ul className="people-list">
          {members?.map((member) => (
            <li key={member.username}>
              <span>
                {member.username}
                {member.username === user?.username && <span className="muted"> (you)</span>}
              </span>
              {host && member.role !== 'owner' ? (
                <span className="actions">
                  <select
                    aria-label={`Role for ${member.username}`}
                    value={member.role}
                    onChange={(event) =>
                      run(() => api.changeRole(room.room_id, member.username, event.target.value as Role))
                    }
                  >
                    <option value="editor">Can edit</option>
                    <option value="viewer">Can view</option>
                  </select>
                  {confirm(member.username, 'Remove', () => api.removeMember(room.room_id, member.username))}
                </span>
              ) : (
                <span className="muted">{member.role === 'owner' ? 'Host' : member.role === 'editor' ? 'Can edit' : 'Can view'}</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <footer className="dialog-foot">
        {host
          ? confirm(
              '#delete',
              'Delete room',
              async () => {
                await api.deleteRoom(room.room_id)
                await desktop?.forgetRoom(room.room_id)
              },
              true,
            )
          : confirm(
              '#leave',
              'Leave room',
              async () => {
                await api.removeMember(room.room_id, user!.username)
                await desktop?.forgetRoom(room.room_id)
              },
              true,
            )}
      </footer>
    </Dialog>
  )
}
