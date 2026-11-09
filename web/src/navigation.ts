// A tiny router on the History API: four routes don't need a dependency (D-102). `navigate`
// pushes a URL and tells every `useLocation` to re-render; Back and Forward arrive as `popstate`.
import { useSyncExternalStore } from 'react'

const CHANGE = 'collab:navigate'

function subscribe(onChange: () => void) {
  window.addEventListener('popstate', onChange)
  window.addEventListener(CHANGE, onChange)
  return () => {
    window.removeEventListener('popstate', onChange)
    window.removeEventListener(CHANGE, onChange)
  }
}

const snapshot = () => window.location.pathname + window.location.search

export function useLocation(): string {
  return useSyncExternalStore(subscribe, snapshot)
}

export function navigate(to: string, { replace = false } = {}) {
  if (replace) window.history.replaceState(null, '', to)
  else window.history.pushState(null, '', to)
  window.dispatchEvent(new Event(CHANGE))
}
