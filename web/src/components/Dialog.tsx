// A modal on the native <dialog>: the browser handles focus trapping, Escape and the backdrop.
import { useEffect, useRef, type ReactNode } from 'react'

export function Dialog({
  title,
  caption,
  onClose,
  children,
  wide = false,
}: {
  title: string
  caption?: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) {
      // jsdom (tests) has no showModal; the open attribute shows it there.
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    }
  }, [])

  return (
    <dialog
      ref={ref}
      className={wide ? 'dialog glass wide' : 'dialog glass'}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => event.target === ref.current && onClose()}
    >
      <div className="dialog-body">
        <header className="dialog-head">
          <div>
            {caption && <p className="caption">( {caption} )</p>}
            <h2>{title}</h2>
          </div>
          <button type="button" className="quiet" onClick={onClose} aria-label="Close">
            Close
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}

/** The server's message for a failed request, announced to screen readers. */
export function ErrorMessage({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p className="error" role="alert">
      {error}
    </p>
  )
}
