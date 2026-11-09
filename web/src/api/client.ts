// Typed wrapper around the FastAPI REST API (#16-#18, #20, #22): one place for the base URL,
// the Bearer header and error parsing. Same origin by default: in production FastAPI serves this
// app, and in dev Vite proxies /api to localhost:8000 (vite.config.ts), so there's no CORS.
const API_URL = import.meta.env.VITE_API_URL ?? ''

export type Role = 'owner' | 'editor' | 'viewer'

export interface User {
  id: number
  username: string
  created_at: string
}

export interface Room {
  room_id: string
  role: Role
  created_at: string
}

export interface Member {
  username: string
  role: Role
  joined_at: string
}

export interface RoomDetail extends Room {
  members: Member[]
}

export interface Invite {
  code: string
  room_id: string
  role: Role
  expires_at: string
}

export interface PresentUser {
  username: string
  role: Role
  connections: number
}

/** A failed request: the HTTP status and the server's message, readable as is. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let currentToken: string | null = null
let onUnauthorized: () => void = () => {}

/** Called by AuthProvider: the token to send, and what to do when the server rejects it. */
export function configureApi(token: string | null, unauthorized: () => void) {
  currentToken = token
  onUnauthorized = unauthorized
}

// FastAPI's `detail` is a string for our own errors and a list for validation errors (422).
function messageOf(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = item.loc?.filter((part) => part !== 'body').join('.')
        return field ? `${field}: ${item.msg}` : (item.msg ?? 'invalid')
      })
      .join('; ')
  }
  return `The server answered ${status}`
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const sentToken = currentToken
  if (sentToken) headers.Authorization = `Bearer ${sentToken}`
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, "Can't reach the server. Is it running?")
  }
  if (response.status === 204) return undefined as T
  const parsed: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    // A rejected token (expired, or the key changed) signs out. A 401 without one is just a
    // failed sign-in, which the form shows.
    if (response.status === 401 && sentToken) onUnauthorized()
    throw new ApiError(response.status, messageOf(response.status, parsed))
  }
  return parsed as T
}

const room = (roomId: string) => `/api/rooms/${encodeURIComponent(roomId)}`

export const api = {
  health: () => request<{ status: string }>('GET', '/health'),

  register: (username: string, password: string) =>
    request<User>('POST', '/api/auth/register', { username, password }),
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>('POST', '/api/auth/login', { username, password }),
  me: () => request<User>('GET', '/api/auth/me'),

  listRooms: () => request<Room[]>('GET', '/api/rooms'),
  createRoom: (roomId: string) => request<Room>('POST', '/api/rooms', { room_id: roomId }),
  getRoom: (roomId: string) => request<RoomDetail>('GET', room(roomId)),
  presence: (roomId: string) =>
    request<{ room_id: string; users: PresentUser[] }>('GET', `${room(roomId)}/presence`),

  createInvite: (roomId: string, role: Role, expiresInHours: number) =>
    request<Invite>('POST', `${room(roomId)}/invites`, {
      role,
      expires_in_hours: expiresInHours,
    }),
  revokeInvite: (roomId: string, code: string) =>
    request<void>('DELETE', `${room(roomId)}/invites/${encodeURIComponent(code)}`),
  joinByInvite: (code: string) =>
    request<{ room_id: string; role: Role }>('POST', `/api/rooms/join/${encodeURIComponent(code)}`),

  changeRole: (roomId: string, username: string, role: Role) =>
    request<Member>('PATCH', `${room(roomId)}/members/${encodeURIComponent(username)}`, { role }),
  removeMember: (roomId: string, username: string) =>
    request<void>('DELETE', `${room(roomId)}/members/${encodeURIComponent(username)}`),
}

/** Room ids, as the server and the socket check them. */
export const ROOM_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
