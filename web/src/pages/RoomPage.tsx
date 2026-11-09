// One room: who's connected now, how to join from Blender, the members, and for owners, invites
// and member management. Presence is polled every few seconds while the tab is visible (D-100).
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { api, ApiError, type Invite, type PresentUser, type Role, type RoomDetail } from '../api/client'
import { CopyButton } from '../components/CopyButton'
import { ErrorMessage } from '../components/ErrorMessage'
import { useAuth } from '../auth'
import { Link } from '../components/Link'
import { inviteLink, serverUrl } from '../links'

const PRESENCE_INTERVAL_MS = 3000
const ROLES: Role[] = ['owner', 'editor', 'viewer']

const message = (caught: unknown) => (caught instanceof ApiError ? caught.message : String(caught))

export function RoomPage({ roomId }: { roomId: string }) {
  const [room, setRoom] = useState<RoomDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    api.getRoom(roomId).then(setRoom, (caught) => setError(message(caught)))
  }, [roomId])

  useEffect(reload, [reload])

  if (error) {
    return (
      <section className="card">
        <h1>{roomId}</h1>
        <ErrorMessage error={error} />
        <p>
          <Link to="/">Back to my rooms</Link>
        </p>
      </section>
    )
  }
  if (!room) return <p className="muted">Loading…</p>

  const owner = room.role === 'owner'
  return (
    <>
      <section className="card">
        <p>
          <Link to="/">← My rooms</Link>
        </p>
        <h1>
          {room.room_id} <span className={`badge ${room.role}`}>{room.role}</span>
        </h1>
        {room.role === 'viewer' && (
          <p className="muted">You're a viewer: you see every edit, but yours aren't sent.</p>
        )}
      </section>
      <Presence roomId={room.room_id} />
      <JoinFromBlender roomId={room.room_id} />
      <Members room={room} owner={owner} onChange={reload} />
      {owner && <Invites roomId={room.room_id} />}
    </>
  )
}

function Presence({ roomId }: { roomId: string }) {
  const [users, setUsers] = useState<PresentUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stopped = false
    const poll = () => {
      if (document.visibilityState !== 'visible') return
      api.presence(roomId).then(
        (result) => {
          if (!stopped) {
            setUsers(result.users)
            setError(null)
          }
        },
        (caught) => !stopped && setError(message(caught)),
      )
    }
    poll()
    const timer = window.setInterval(poll, PRESENCE_INTERVAL_MS)
    document.addEventListener('visibilitychange', poll) // catch up as soon as it's shown again
    return () => {
      stopped = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', poll)
    }
  }, [roomId])

  return (
    <section className="card" aria-labelledby="presence-heading">
      <h2 id="presence-heading">Connected now</h2>
      <ErrorMessage error={error} />
      {users === null && !error && <p className="muted">Checking…</p>}
      {users?.length === 0 && <p className="muted">Nobody is connected from Blender right now.</p>}
      {users && users.length > 0 && (
        <ul className="list">
          {users.map((user) => (
            <li key={user.username}>
              <span>
                <span className="dot" aria-hidden="true" /> {user.username}
                {user.connections > 1 && (
                  <span className="muted"> · {user.connections} connections</span>
                )}
              </span>
              <span className={`badge ${user.role}`}>{user.role}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function JoinFromBlender({ roomId }: { roomId: string }) {
  const url = serverUrl()
  return (
    <section className="card">
      <h2>Join from Blender</h2>
      <p>
        In Blender: Edit › Preferences › Add-ons › Collaborative. Set the Server URL, sign in to the
        add-on with this same account, then Join this room from the Collaborative panel.
      </p>
      <dl className="copy-fields">
        <dt>Room ID</dt>
        <dd>
          <code>{roomId}</code> <CopyButton text={roomId} label="Copy room ID" />
        </dd>
        <dt>Server URL</dt>
        <dd>
          <code>{url}</code> <CopyButton text={url} label="Copy server URL" />
        </dd>
      </dl>
    </section>
  )
}

function Members({
  room,
  owner,
  onChange,
}: {
  room: RoomDetail
  owner: boolean
  onChange: () => void
}) {
  const { user } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)

  async function run(action: Promise<unknown>) {
    setError(null)
    try {
      await action
      onChange()
    } catch (caught) {
      setError(message(caught))
    }
    setConfirming(null)
  }

  return (
    <section className="card">
      <h2>Members</h2>
      <ErrorMessage error={error} />
      <ul className="list">
        {room.members.map((member) => (
          <li key={member.username}>
            <span>
              {member.username}
              {member.username === user?.username && <span className="muted"> (you)</span>}
            </span>
            {owner ? (
              <span className="actions">
                <select
                  aria-label={`Role for ${member.username}`}
                  value={member.role}
                  onChange={(event) =>
                    run(api.changeRole(room.room_id, member.username, event.target.value as Role))
                  }
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
                {confirming === member.username ? (
                  <button
                    type="button"
                    className="danger"
                    onClick={() => run(api.removeMember(room.room_id, member.username))}
                  >
                    Confirm remove
                  </button>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setConfirming(member.username)}
                  >
                    Remove
                  </button>
                )}
              </span>
            ) : (
              <span className={`badge ${member.role}`}>{member.role}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Invites({ roomId }: { roomId: string }) {
  const [role, setRole] = useState<Role>('editor')
  const [hours, setHours] = useState(24)
  // The server shows a code only once, so this page lists the ones made here.
  const [invites, setInvites] = useState<(Invite & { revoked?: boolean })[]>([])
  const [error, setError] = useState<string | null>(null)

  async function create(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const invite = await api.createInvite(roomId, role, hours)
      setInvites((current) => [invite, ...current])
    } catch (caught) {
      setError(message(caught))
    }
  }

  async function revoke(code: string) {
    setError(null)
    try {
      await api.revokeInvite(roomId, code)
      setInvites((current) =>
        current.map((invite) => (invite.code === code ? { ...invite, revoked: true } : invite)),
      )
    } catch (caught) {
      setError(message(caught))
    }
  }

  return (
    <section className="card">
      <h2>Invite someone</h2>
      <form onSubmit={create} className="inline-form">
        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="editor">editor</option>
            <option value="viewer">viewer</option>
          </select>
        </label>
        <label>
          Expires in (hours)
          <input
            type="number"
            min={1}
            max={720}
            required
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          />
        </label>
        <button type="submit">Create invite link</button>
      </form>
      <ErrorMessage error={error} />
      {invites.length > 0 && (
        <ul className="list invites">
          {invites.map((invite) => {
            const link = inviteLink(invite.code)
            return (
              <li key={invite.code}>
                <span>
                  <code className={invite.revoked ? 'revoked' : undefined}>{link}</code>
                  <span className="muted">
                    {' '}
                    {invite.role}
                    {invite.revoked
                      ? ', revoked'
                      : `, until ${new Date(invite.expires_at).toLocaleString()}`}
                  </span>
                </span>
                {!invite.revoked && (
                  <span className="actions">
                    <CopyButton text={link} label="Copy link" />
                    <button type="button" className="secondary" onClick={() => revoke(invite.code)}>
                      Revoke
                    </button>
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <p className="hint">Anyone with a link can join with its role until it expires or you revoke it.</p>
    </section>
  )
}
