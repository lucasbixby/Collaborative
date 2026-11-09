// The shell: the header with who's signed in, and the page for the current URL. Signed out,
// every URL shows the sign-in form, so signing in lands you on the page you asked for.
import { useAuth } from './auth'
import { JoinPage } from './pages/JoinPage'
import { RoomPage } from './pages/RoomPage'
import { RoomsPage } from './pages/RoomsPage'
import { SignInPage } from './pages/SignInPage'
import { Link } from './components/Link'
import { useLocation } from './navigation'

function Page({ path }: { path: string }) {
  const room = path.match(/^\/rooms\/([^/]+)\/?$/)
  if (room) return <RoomPage roomId={decodeURIComponent(room[1])} />
  const join = path.match(/^\/join\/([^/]+)\/?$/)
  if (join) return <JoinPage code={decodeURIComponent(join[1])} />
  if (path === '/') return <RoomsPage />
  return (
    <section className="card">
      <h1>Not found</h1>
      <p>
        <Link to="/">Go to my rooms</Link>
      </p>
    </section>
  )
}

function App() {
  const { user, checking, checkError, signOut } = useAuth()
  const path = useLocation().split('?')[0]

  let content
  if (checkError) {
    content = (
      <section className="card narrow">
        <p className="error" role="alert">
          {checkError}
        </p>
        <button type="button" onClick={() => window.location.reload()}>
          Try again
        </button>
      </section>
    )
  } else if (checking) {
    content = <p className="muted">Loading…</p>
  } else if (!user) {
    content = (
      <SignInPage
        intro={
          path.startsWith('/join/')
            ? "You've been invited to a room. Sign in, or create an account, to join it."
            : undefined
        }
      />
    )
  } else {
    content = <Page key={path} path={path} />
  }

  return (
    <>
      <header className="site-header">
        <Link to="/">Collaborative</Link>
        {user && (
          <span className="who">
            <span>
              Signed in as <strong>{user.username}</strong>
            </span>
            <button type="button" className="secondary" onClick={signOut}>
              Sign out
            </button>
          </span>
        )}
      </header>
      <main>{content}</main>
    </>
  )
}

export default App
