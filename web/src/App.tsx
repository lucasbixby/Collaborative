// The shell: the header with who's signed in, then the sign-in page or the dashboard.
import { useState } from 'react'

import { useAuth } from './auth'
import { SettingsDialog } from './components/SettingsDialog'
import { Dashboard } from './pages/Dashboard'
import { SignInPage } from './pages/SignInPage'
import { desktop } from './platform'

function App() {
  const { user, checking, checkError, signOut } = useAuth()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const openSettings = desktop ? () => setSettingsOpen(true) : undefined

  let content
  if (checkError) {
    content = (
      <section className="notice">
        <p className="error" role="alert">
          {checkError}
        </p>
        <div className="actions">
          <button type="button" className="primary" onClick={() => window.location.reload()}>
            Try again
          </button>
          {openSettings && (
            <button type="button" className="outline" onClick={openSettings}>
              Settings
            </button>
          )}
        </div>
      </section>
    )
  } else if (checking) {
    content = <p className="muted">Loading…</p>
  } else if (!user) {
    content = <SignInPage onSettings={openSettings} />
  } else {
    content = <Dashboard />
  }

  return (
    <div className="page">
      {user && (
        <header className="site-header">
          <span className="brand">Collaborative</span>
          <nav>
            <span className="caption">( {user.username} )</span>
            {openSettings && (
              <button type="button" className="quiet" onClick={openSettings}>
                Settings
              </button>
            )}
            <button type="button" className="quiet" onClick={signOut}>
              Log out
            </button>
          </nav>
        </header>
      )}
      <main>{content}</main>
      {settingsOpen && (
        <SettingsDialog
          onClose={() => setSettingsOpen(false)}
          onSaved={() => window.location.reload()}
        />
      )}
    </div>
  )
}

export default App
