// URLs this page hands to people: the socket URL for the add-on, and invite links.

/** The socket URL for the add-on's preferences: this page's own host, as ws:// or wss://. */
export function serverUrl(location: Location = window.location): string {
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
}

export function inviteLink(code: string, location: Location = window.location): string {
  return `${location.origin}/join/${encodeURIComponent(code)}`
}
