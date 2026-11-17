// Log in, or create an account and then log in, on one form. The server's own messages are
// shown as they come.
import { useState, type FormEvent } from 'react'

import { api, ApiError } from '../api/client'
import { useAuth } from '../auth'
import { ErrorMessage } from '../components/Dialog'
import { DotField } from '../components/DotField'

export function SignInPage({ onSettings }: { onSettings?: () => void }) {
  const { signIn } = useAuth()
  const [registering, setRegistering] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (registering) await api.register(username, password)
      await signIn(username, password)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught))
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <h1 className="wordmark" aria-label="Collaborative">
        Collaborative
      </h1>
      <div className="signin-grid">
        <div className="signin-art">
          <DotField name={registering ? 'new here' : 'welcome back'} columns={10} rows={7} />
          <p className="caption">( One Blender scene, edited by several people at once )</p>
        </div>
        <form className="signin-form" onSubmit={submit}>
          <h2>{registering ? 'Create an account' : 'Log in'}</h2>
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          {registering && <p className="hint">3–32 letters, digits, ".", "_" or "-".</p>}
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={registering ? 'new-password' : 'current-password'}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {registering && <p className="hint">At least 8 characters.</p>}
          <ErrorMessage error={error} />
          <button type="submit" className="primary" disabled={busy}>
            {registering ? 'Create account' : 'Log in'}
          </button>
          <p className="switch">
            {registering ? 'Already have an account?' : 'New here?'}{' '}
            <button
              type="button"
              className="link"
              onClick={() => {
                setRegistering(!registering)
                setError(null)
              }}
            >
              {registering ? 'Log in' : 'Create an account'}
            </button>
          </p>
          {onSettings && (
            <button type="button" className="link" onClick={onSettings}>
              Server settings
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
