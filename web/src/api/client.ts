// Typed wrapper around the server's REST API: one place for the base URL, the Bearer header and
// error parsing. In a browser the server is this page's own origin; the desktop app sets the
// address from its settings.
export type Role = 'owner' | 'editor' | 'viewer'

export interface User {
  id: number
  username: string
  created_at: string
}

export interface RoomFile {
  name: string
  size: number
  hash: string
  updated_at: string
}

export interface PresentUser {
  username: string
  role: Role
  connections: number
}

export interface SaveRequest {
  id: string
  username: string
  requested_at: string
}

export interface Room {
  room_id: string
  role: Role
  host: string
  created_at: string
  file: RoomFile | null
  online: PresentUser[]
  save_requests: SaveRequest[]
}

export interface Member {
  username: string
  role: Role
  joined_at: string
}

export interface RoomDetail extends Room {
  members: Member[]
}

/** A failed request: the HTTP status and the server's message, readable as is. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let baseUrl = ''
let currentToken: string | null = null
let onUnauthorized: () => void = () => {}

export function setServerUrl(url: string) {
  baseUrl = url.replace(/\/+$/, '')
}

export const serverUrl = () => baseUrl

/** Called by AuthProvider: the token to send, and what to do when the server rejects it. */
export function configureApi(token: string | null, unauthorized: () => void) {
  currentToken = token
  onUnauthorized = unauthorized
}

// FastAPI's `detail` is a string for our own errors and a list for validation errors (422).
function messageOf(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail.charAt(0).toUpperCase() + detail.slice(1)
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

async function request<T>(method: string, path: string, body?: unknown, raw?: Blob): Promise<T> {
  const headers: Record<string, string> = {}
  if (raw) headers['Content-Type'] = 'application/octet-stream'
  else if (body !== undefined) headers['Content-Type'] = 'application/json'
  const sentToken = currentToken
  if (sentToken) headers.Authorization = `Bearer ${sentToken}`
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
    })
  } catch {
    throw new ApiError(0, "Can't reach the server. Check its address in Settings, and that it's running.")
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
  register: (username: string, password: string) =>
    request<User>('POST', '/api/auth/register', { username, password }),
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>('POST', '/api/auth/login', { username, password }),
  me: () => request<User>('GET', '/api/auth/me'),

  listRooms: () => request<Room[]>('GET', '/api/rooms'),
  hostRoom: (roomId: string, password: string) =>
    request<Room>('POST', '/api/rooms', { room_id: roomId, password }),
  joinRoom: (roomId: string, password: string) =>
    request<Room>('POST', '/api/rooms/join', { room_id: roomId, password }),
  getRoom: (roomId: string) => request<RoomDetail>('GET', room(roomId)),
  deleteRoom: (roomId: string) => request<void>('DELETE', room(roomId)),
  uploadFile: (roomId: string, file: File) =>
    request<RoomFile>('PUT', `${room(roomId)}/file?name=${encodeURIComponent(file.name)}`, undefined, file),

  changeRole: (roomId: string, username: string, role: Role) =>
    request<Member>('PATCH', `${room(roomId)}/members/${encodeURIComponent(username)}`, { role }),
  removeMember: (roomId: string, username: string) =>
    request<void>('DELETE', `${room(roomId)}/members/${encodeURIComponent(username)}`),

  answerSave: (roomId: string, requestId: string, approve: boolean) =>
    request<void>('POST', `${room(roomId)}/save-requests/${encodeURIComponent(requestId)}`, { approve }),
}

/** Room names, as the server checks them. */
export const ROOM_NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
