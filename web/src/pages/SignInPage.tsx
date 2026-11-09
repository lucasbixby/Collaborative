// Sign in, or register and then sign in, on one form. The server's own messages are shown as
// they come ("wrong username or password", "that username is taken", the validation rules).
import { useState, type FormEvent } from 'react'

import { api, ApiError } from '../api/client'
import { ErrorMessage } from '../components/ErrorMessage'
import { useAuth } from '../auth'

export function SignInPage({ intro }: { intro?: string }) {
  const { signIn } = useAuth()
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const registering = mode === 'register'

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
    <section className="card narrow">
      <h1>{registering ? 'Create an account' : 'Sign in'}</h1>
      {intro && <p>{intro}</p>}
      <form onSubmit={submit}>
        <label>
          Username
          <input
            name="username"
            autoComplete="username"
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
        <button type="submit" disabled={busy}>
          {registering ? 'Create account' : 'Sign in'}
        </button>
      </form>
      <p>
        {registering ? 'Already have an account? ' : 'New here? '}
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(registering ? 'signin' : 'register')
            setError(null)
          }}
        >
          {registering ? 'Sign in' : 'Create an account'}
        </button>
      </p>
    </section>
  )
}
