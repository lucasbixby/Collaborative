// What must be known before the first render. In the desktop app that's the server's address,
// from its settings: nothing can be asked of the server until then.
import { setServerUrl } from './api/client'
import { desktop } from './platform'

export async function boot() {
  if (desktop) setServerUrl((await desktop.getSettings()).serverUrl)
}
