// Desktop app settings: which server to use, and where Blender is if it wasn't found.
import { useEffect, useState, type FormEvent } from 'react'

import { desktop, type DesktopSettings } from '../platform'
import { Dialog } from './Dialog'

export function SettingsDialog({ onClose, onSaved }: { onClose: () => void; onSaved: (settings: DesktopSettings) => void }) {
  const [server, setServer] = useState('')
  const [blender, setBlender] = useState('')
  const [detected, setDetected] = useState('')

  useEffect(() => {
    desktop!.getSettings().then((settings) => {
      setServer(settings.serverUrl)
      setBlender(settings.blenderPath)
      setDetected(settings.detectedBlender)
    })
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    onSaved(await desktop!.saveSettings({ serverUrl: server.trim() }))
  }

  async function browse() {
    const chosen = await desktop!.pickBlender()
    if (chosen) setBlender(chosen)
  }

  return (
    <Dialog title="Settings" onClose={onClose}>
      <form onSubmit={submit}>
        <label>
          Server address
          <input name="server" required value={server} onChange={(event) => setServer(event.target.value)} />
        </label>
        <p className="hint">Where the Collaborative server runs, for example http://192.168.1.20:8000.</p>
        <div className="field">
          <span className="field-label">Blender</span>
          <div className="file-row">
            <button type="button" className="outline" onClick={browse}>
              Choose Blender
            </button>
            <span className="file-name">{blender || detected || 'Not found yet'}</span>
          </div>
          {!blender && detected && <p className="hint">Found automatically.</p>}
        </div>
        <button type="submit" className="primary">
          Save settings
        </button>
      </form>
    </Dialog>
  )
}
