// An in-app link: a real <a href> (so it can be opened in a new tab or copied), which moves
// within the app on a plain click instead of reloading the page.
import type { MouseEvent, ReactNode } from 'react'

import { navigate } from '../navigation'

export function Link({ to, children }: { to: string; children: ReactNode }) {
  function onClick(event: MouseEvent<HTMLAnchorElement>) {
    // Let the browser handle a new tab or window (Cmd/Ctrl/Shift-click, middle click).
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to)
  }
  return (
    <a href={to} onClick={onClick}>
      {children}
    </a>
  )
}
