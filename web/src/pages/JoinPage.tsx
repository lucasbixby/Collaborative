// /join/<code>: an invite link. Signed out, it asks you to sign in or register first (App shows
// the sign-in form with this page's intro); signed in, it joins and goes to the room.
import { useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../api/client'
import { ErrorMessage } from '../components/ErrorMessage'
import { Link } from '../components/Link'
import { navigate } from '../navigation'

export function JoinPage({ code }: { code: string }) {
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return // StrictMode runs effects twice in dev; join once
    started.current = true
    api.joinByInvite(code).then(
      (joined) => navigate(`/rooms/${encodeURIComponent(joined.room_id)}`, { replace: true }),
      (caught: ApiError) =>
        setError(caught.status === 404 ? "This invite link doesn't exist." : caught.message),
    )
  }, [code])

  return (
    <section className="card narrow">
      <h1>Joining a room</h1>
      {error ? (
        <>
          <ErrorMessage error={error} />
          <p>Ask the room's owner for a new link.</p>
          <p>
            <Link to="/">Go to my rooms</Link>
          </p>
        </>
      ) : (
        <p className="muted">Joining…</p>
      )}
    </section>
  )
}
