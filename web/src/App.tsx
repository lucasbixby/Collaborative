import { useEffect, useState } from 'react'
import { getHealth } from './api/client'

// Placeholder shell. Pages planned in src/pages/: SignIn, Rooms (create / join / invite), RoomStatus.
function App() {
  const [server, setServer] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    getHealth()
      .then(() => setServer('online'))
      .catch(() => setServer('offline'))
  }, [])

  return (
    <main>
      <h1>Collaborative</h1>
      <p>Server: {server}</p>
    </main>
  )
}

export default App
