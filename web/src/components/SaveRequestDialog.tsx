// The host's pop-up when someone else saves in Blender. Approve saves the host's own file from
// the host's Blender; Deny leaves it alone.
import { useState } from 'react'

import { api, ApiError, type Room, type SaveRequest } from '../api/client'
import { Dialog, ErrorMessage } from './Dialog'

export function SaveRequestDialog({
  room,
  request,
  onAnswered,
}: {
  room: Room
  request: SaveRequest
  onAnswered: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function answer(approve: boolean) {
    setBusy(true)
    setError(null)
    try {
      await api.answerSave(room.room_id, request.id, approve)
      onAnswered()
    } catch (caught) {
      // 404: it expired or was answered from another window; the next refresh drops it.
      if ((caught as ApiError).status === 404) onAnswered()
      else setError((caught as ApiError).message)
      setBusy(false)
    }
  }

  return (
    <Dialog title={`${request.username} would like to save the project`} caption={room.room_id} onClose={() => answer(false)}>
      <p>Approving saves your file{room.file ? `, ${room.file.name},` : ''} from your Blender.</p>
      <ErrorMessage error={error} />
      <div className="actions">
        <button type="button" className="primary" disabled={busy} onClick={() => answer(true)}>
          Approve
        </button>
        <button type="button" className="outline" disabled={busy} onClick={() => answer(false)}>
          Deny
        </button>
      </div>
    </Dialog>
  )
}
