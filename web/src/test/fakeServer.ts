// A fake `fetch` for the UI tests: routes keyed by "METHOD /path" answer with a status and a JSON
// body, and every call is recorded. No real server, and no network.
import { vi } from 'vitest'

type Reply = { status: number; body?: unknown } | ((request: Recorded) => { status: number; body?: unknown })

export interface Recorded {
  method: string
  path: string
  body: unknown
  authorization: string | null
}

export function fakeServer(routes: Record<string, Reply>) {
  const calls: Recorded[] = []
  const fetch = vi.fn(async (url: string, init: RequestInit = {}) => {
    const headers = (init.headers ?? {}) as Record<string, string>
    const recorded: Recorded = {
      method: init.method ?? 'GET',
      path: url,
      body: init.body ? JSON.parse(init.body as string) : undefined,
      authorization: headers.Authorization ?? null,
    }
    calls.push(recorded)
    const route = routes[`${recorded.method} ${url}`]
    if (!route) return new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 })
    const reply = typeof route === 'function' ? route(recorded) : route
    if (reply.status === 204) return new Response(null, { status: 204 })
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetch)
  return { calls }
}

export const ALICE = { id: 1, username: 'alice', created_at: '2026-11-09T12:00:00Z' }

export const signedIn = (token = 'tok-alice') => window.sessionStorage.setItem('collab.token', token)
