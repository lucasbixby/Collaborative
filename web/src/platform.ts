// What the desktop app adds to the page. The Electron preload script (desktop/preload.cjs)
// exposes `window.collab`; in a plain browser it's absent, and the UI falls back to what a page
// can do: upload a file the user picks, but not launch Blender or remember a file's path.

export interface PickedFile {
  /** An opaque handle for the file the user chose; the path itself stays in the app. */
  id: string
  name: string
  size: number
}

export interface DesktopSettings {
  serverUrl: string
  blenderPath: string
  /** The Blender the app found on its own, used when `blenderPath` is empty. */
  detectedBlender: string
}

export interface LaunchRequest {
  serverUrl: string
  token: string
  username: string
  roomId: string
  role: string
  fileHash: string
  fileName: string
}

export interface DesktopBridge {
  getSettings(): Promise<DesktopSettings>
  saveSettings(settings: { serverUrl: string }): Promise<DesktopSettings>
  pickBlendFile(): Promise<PickedFile | null>
  /** Asks for Blender's location and saves it. Null if cancelled or it isn't a program. */
  pickBlender(): Promise<string | null>
  /** Uploads a picked file as the room's project and remembers it as this room's local file. */
  hostFile(request: { serverUrl: string; token: string; roomId: string; fileId: string }): Promise<void>
  launch(request: LaunchRequest): Promise<void>
  forgetRoom(roomId: string): Promise<void>
  notify(title: string, body: string): void
  onProgress(listener: (message: string) => void): () => void
}

declare global {
  interface Window {
    collab?: DesktopBridge
  }
}

export const desktop: DesktopBridge | null = typeof window !== 'undefined' ? (window.collab ?? null) : null
