// Thin wrapper around the FastAPI REST API.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

export function getHealth() {
  return request<{ status: string }>('/health')
}

// TODO: login, register, listRooms, createRoom, createInvite, joinRoom
